import json
from pathlib import Path

import pytest

from jobfleet.llm import ClaudeResult, ClaudeRunner, in_backoff, parse_envelope
from jobfleet.models import JobResult
from jobfleet.pipeline import RunBuckets
from jobfleet.profile import load_profile
from jobfleet.scout import run_scout, scout_due
from jobfleet.state import StateStore
from jobfleet.triage import SCHEMA, run_triage

CONFIG = Path(__file__).resolve().parents[1] / "config"


def envelope(**kw):
    base = {"type": "result", "subtype": "success", "is_error": False, "result": ""}
    base.update(kw)
    return json.dumps(base)


def test_parse_envelope_success_and_failures():
    good = parse_envelope(envelope(structured_output={"verdicts": []}), "", 0, SCHEMA)
    assert good.ok and good.data == {"verdicts": []}
    revoked = parse_envelope(envelope(is_error=True, api_error_status=401, result="Failed to authenticate. OAuth access token has been revoked."), "", 1, SCHEMA)
    assert not revoked.ok and revoked.kind == "auth"
    limited = parse_envelope(envelope(is_error=True, result="Claude AI usage limit reached"), "", 1, SCHEMA)
    assert limited.kind == "limit"
    assert parse_envelope("not json", "boom", 1, SCHEMA).kind == "invalid"
    wrong = parse_envelope(envelope(structured_output={"verdicts": [{"id": "1"}]}), "", 0, SCHEMA)
    assert not wrong.ok and wrong.kind == "invalid"


def test_runner_handles_missing_cli_and_kill_switch(tmp_path, monkeypatch):
    runner = ClaudeRunner(tmp_path / "sandbox")
    monkeypatch.setenv("JOBFLEET_CLAUDE_EXE", str(tmp_path / "nope.exe"))
    assert runner.run("hi", SCHEMA).kind == "missing"
    monkeypatch.setenv("JOBFLEET_DISABLE_LLM", "1")
    assert runner.run("hi", SCHEMA).kind == "disabled"


def row(key, tier="needs_review", category="data_bi"):
    return JobResult(company="Acme", title="Analyst", experience_required="", url=f"https://x/{key}", system_notes="", category_id=category,
                     score=50, source="lever", location="Pune", matched_terms=[], retrieved_at="", quality_tier=tier, key=key)


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def run(self, prompt, schema, **kw):
        self.calls += 1
        assert "untrusted" in prompt
        return self.result


def test_triage_promotes_demotes_and_caches(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    buckets = RunBuckets(main={"data_bi": [row("m1"), row("m2", tier="high_confidence")], "research": [], "excel_mis": []},
                         possible={"data_bi": [row("p1", tier="possible_match")], "research": [], "excel_mis": []})
    verdicts = {"verdicts": [
        {"id": "0", "relevant": True, "category": "research", "early_career_fit": "yes", "confidence": 0.9, "reason": "market research role"},
        {"id": "1", "relevant": False, "category": "none", "early_career_fit": "no", "confidence": 0.95, "reason": "people manager"},
    ]}
    runner = FakeRunner(ClaudeResult(True, data=verdicts))
    summary = run_triage(runner, buckets, state, {"triage": {}}, tmp_path)
    assert "1 promoted, 1 demoted" in summary
    assert [r.key for r in buckets.main["research"]] == ["p1"] and buckets.main["research"][0].quality_tier == "claude_promoted"
    assert [r.key for r in buckets.main["data_bi"]] == ["m2"]  # high-confidence rows are never sent
    assert (tmp_path / "audit" / "claude_review.csv").exists()
    second = FakeRunner(ClaudeResult(True, data={"verdicts": []}))
    run_triage(second, RunBuckets(main={"data_bi": [row("m1")]}, possible={}), state, {"triage": {}}, tmp_path)
    assert second.calls == 0  # verdict cached


@pytest.mark.parametrize("config_source", ["shipped", "defaults"])
def test_triage_keeps_rows_below_the_demotion_threshold(tmp_path, config_source):
    # 2026-11-13: Capgemini 'Order Management Specialist' (3-5 / 5-7 yrs) was demoted at 0.80,
    # although the user's rule accepts ranges that start at 3. Demotion now needs >= 0.85.
    state = StateStore(tmp_path / "s.sqlite")
    buckets = RunBuckets(main={"excel_mis": [row("m1", category="excel_mis")]}, possible={})
    verdict = {"verdicts": [{"id": "0", "relevant": False, "category": "none", "early_career_fit": "unclear", "confidence": 0.8, "reason": "asks 3-5 or 5-7 years"}]}
    config = load_profile(CONFIG.parent / "profile.toml").ai if config_source == "shipped" else {"triage": {}}
    summary = run_triage(FakeRunner(ClaudeResult(True, data=verdict)), buckets, state, config, tmp_path)
    assert "0 demoted" in summary
    kept = buckets.main["excel_mis"]
    assert [r.key for r in kept] == ["m1"] and "Claude: doubtful (0.80)" in kept[0].system_notes


def test_triage_failure_sets_backoff_and_does_not_raise(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    buckets = RunBuckets(main={"data_bi": [row("m1")]}, possible={})
    runner = FakeRunner(ClaudeResult(False, error="401 revoked", kind="auth"))
    assert "claude auth login" in run_triage(runner, buckets, state, {"triage": {}}, tmp_path)
    assert in_backoff(state)
    assert [r.key for r in buckets.main["data_bi"]] == ["m1"]


def test_scout_due_and_failure_path(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    assert scout_due(state, 7)
    state.set_meta("scout_last_success", "2099-01-01T00:00:00+00:00")
    assert not scout_due(state, 7) and scout_due(state, 7, force=True)
    runner = FakeRunner(ClaudeResult(False, error="Claude Code CLI not found", kind="missing"))
    runner.run = lambda prompt, schema, **kw: ClaudeResult(False, error="Claude Code CLI not found", kind="missing")
    message = run_scout(runner, CONFIG, tmp_path, state, None, None, [], {"scout": {}}, [], force=True)
    assert message.startswith("failed")
