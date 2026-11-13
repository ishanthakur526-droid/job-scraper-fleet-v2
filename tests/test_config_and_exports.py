import json
from pathlib import Path

from jobfleet.config import load_boards, load_llm_config, load_taxonomy
from jobfleet.exporters import MAIN_COLUMNS, export_category, main_row
from jobfleet.models import Category, JobResult
from jobfleet.sources import ADAPTERS

CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_shipped_config_is_consistent():
    boards, _seeds = load_boards(CONFIG, include_disabled=True)
    assert boards, "no boards configured"
    assert all(board.source in ADAPTERS for board in boards)
    keys = [board.key for board in boards]
    assert len(keys) == len(set(keys))
    categories, adjacent = load_taxonomy(CONFIG)
    assert [c.id for c in categories] == ["data_bi", "research", "excel_mis"] and adjacent.id == "adjacent"
    assert load_llm_config(CONFIG)["triage"]["max_items"] > 0


def test_load_boards_merges_discovered_and_skips_disabled(tmp_path):
    (tmp_path / "boards.json").write_text(json.dumps({"boards": [
        {"company": "Manual", "source": "lever", "token": "manual"},
        {"company": "Off", "source": "lever", "token": "off", "enabled": False},
    ]}), encoding="utf-8")
    (tmp_path / "discovered_boards.json").write_text(json.dumps({"boards": [{"company": "Generated", "source": "ashby", "token": "generated"}]}), encoding="utf-8")
    boards, _ = load_boards(tmp_path)
    assert [(b.source, b.token) for b in boards] == [("lever", "manual"), ("ashby", "generated")]


def test_main_csv_keeps_legacy_columns_first_and_has_bom(tmp_path):
    category = Category(id="data_bi", name="Data & BI", output="data_bi_roles_today.csv")
    item = JobResult(company="Zoë Analytics", title="Data Analyst – Insights", experience_required="1-3 years", url="https://x/1",
                     system_notes="", category_id="data_bi", score=80, source="lever", location="Pune", matched_terms=[], retrieved_at="",
                     quality_tier="high_confidence", posted_date="2026-11-12", first_seen="2026-11-13T10:00:00+00:00")
    legacy, _audit = export_category(tmp_path, category, [item])
    raw = legacy.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # Excel needs the BOM to show non-ASCII text correctly
    header = raw.decode("utf-8-sig").splitlines()[0].split(",")
    assert header[:5] == ["Company", "Exact Role Name", "Experience Required", "Application Link", "System Notes"]
    assert header == MAIN_COLUMNS
    assert main_row(item)["First Seen"] == "2026-11-13"
