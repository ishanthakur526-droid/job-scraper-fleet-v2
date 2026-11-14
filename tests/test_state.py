import csv
import os
from datetime import datetime, timedelta, timezone

from jobfleet.models import BoardHealth, JobResult, RawJob, legacy_url_key
from jobfleet.state import StateStore

AMAZON_UUID_URL = "https://www.amazon.jobs/en/jobs/cb6affc4-b34f-49c9-ba58-e8aa43e1afc5"


def result(key, url="https://example.com/1", legacy=(), group=(), board="lever|acme", source="lever"):
    return JobResult(
        company="Acme", title="Data Analyst", experience_required="1-3 years", url=url, system_notes="",
        category_id="data_bi", score=80, source=source, location="Pune", matched_terms=[], retrieved_at="",
        quality_tier="high_confidence", key=key, board_key=board, legacy_keys=list(legacy), group_keys=list(group),
    )


def test_first_seen_only_once(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    first = [result("lever:1")]
    assert state.record_results(first) == 1 and first[0].is_new
    second = [result("lever:1")]
    assert state.record_results(second) == 0 and not second[0].is_new
    assert second[0].first_seen == first[0].first_seen


def test_legacy_csv_import_and_amazon_key_migration(tmp_path):
    history = tmp_path / "job_history.csv"
    with history.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Job Key", "First Seen At", "Last Seen At", "Seen Count", "Active", "Source"])
        writer.writeheader()
        writer.writerow({"Job Key": legacy_url_key(AMAZON_UUID_URL), "First Seen At": "2026-09-21T10:00:00+00:00", "Last Seen At": "2026-11-12T10:00:00+00:00", "Seen Count": "9", "Active": "yes", "Source": "amazon_jobs"})
    state = StateStore(tmp_path / "s.sqlite")
    assert state.import_legacy_history(history) == 1
    assert state.import_legacy_history(history) == 0  # one-time
    assert (tmp_path / "job_history.v2_backup.csv").exists()
    migrated = result("amazon_jobs:10593289", url="https://www.amazon.jobs/en/jobs/10593289/x", legacy=[legacy_url_key(AMAZON_UUID_URL)], board="amazon_jobs|analyst", source="amazon_jobs")
    state.record_results([migrated])
    assert not migrated.is_new and migrated.first_seen.startswith("2026-09-21")
    again = result("amazon_jobs:10593289", url="https://www.amazon.jobs/en/jobs/10593289/x", board="amazon_jobs|analyst", source="amazon_jobs")
    state.record_results([again])
    assert not again.is_new


def test_legacy_row_is_claimed_only_once(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    state.record_results([result("https://example.com/old")])
    state._claimed.clear()  # new run
    a = result("lever:a", legacy=["https://example.com/old"])
    b = result("lever:b", legacy=["https://example.com/old"])
    state.record_results([a, b])
    assert not a.is_new and b.is_new


def test_missing_only_when_board_succeeded(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    state.record_results([result("lever:1", board="lever|acme")])
    assert state.mark_presence([], succeeded_boards=set(), succeeded_sources=set()) == 0  # board failed: untouched
    assert state.counts()["active"] == 1
    assert state.mark_presence([], succeeded_boards={"lever|acme"}, succeeded_sources={"lever"}) == 1
    assert state.counts()["active"] == 0
    live = RawJob("Acme", "Data Analyst", "Pune", "https://example.com/1", "", "lever", source_id="1")
    state.mark_presence([live], succeeded_boards={"lever|acme"}, succeeded_sources={"lever"})
    assert state.counts()["active"] == 1


def test_group_member_keys_are_remembered(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    state.record_results([result("amazon_jobs:1", group=["amazon_jobs:2", "amazon_jobs:3"])])
    later = [result("amazon_jobs:2")]
    state.record_results(later)
    assert not later[0].is_new


def test_quarantine_after_three_hard_failures(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    health = BoardHealth("Dead", "lever", "dead", "failed", hard_failure=True, board_key="lever|dead")
    soft = BoardHealth("Flaky", "workday", "x", "failed", hard_failure=False, board_key="workday|x")
    for _ in range(3):
        state.update_board(health)
        state.update_board(soft)
    quarantined = state.quarantined()
    assert "lever|dead" in quarantined and "workday|x" not in quarantined
    assert state.quarantined(now=datetime.now(timezone.utc) + timedelta(days=15)) == {}
    state.update_board(BoardHealth("Dead", "lever", "dead", "ok", board_key="lever|dead"))
    assert state.quarantined() == {}


def test_prune_old_inactive_rows(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    old = datetime.now(timezone.utc) - timedelta(days=400)
    state.record_results([result("lever:old")], now=old)
    state.mark_presence([], {"lever|acme"}, {"lever"}, now=old)
    assert state.prune() == 1


def test_csv_views_survive_a_locked_file(tmp_path, monkeypatch):
    state = StateStore(tmp_path / "s.sqlite")
    state.record_results([result("lever:1")])
    real_replace = os.replace

    def locked(src, dst):
        if str(dst).endswith("job_history.csv"):
            raise PermissionError("locked by Excel")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", locked)
    written = state.export_csv_views(tmp_path)
    assert any(p.name == "job_history_copy.csv" for p in written)


def test_people_facing_ledger_is_written_to_outputs(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    state.record_results([result("lever:1")])
    out = tmp_path / "outputs"
    state.export_csv_views(tmp_path / "state", out)
    ledger = (out / "job_history.csv").read_text(encoding="utf-8-sig").splitlines()
    assert ledger[0].startswith("Still Open,Company,Exact Role Name,Family") and ledger[1].startswith("yes,")
