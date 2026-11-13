import json
import tomllib
from pathlib import Path

import pytest

from jobfleet.companies import load_my_companies, parse_line
from jobfleet.config import expand_boards, load_boards
from jobfleet.dashboard import build_data, render
from jobfleet.models import Board, BoardHealth, JobResult
from jobfleet.pipeline import RunBuckets
from jobfleet.profile import load_profile, profile_from_dict
from jobfleet.profile_writer import Choices
from jobfleet.profile_writer import render as render_profile
from jobfleet.role_library import FAMILIES, find
from jobfleet.setup_wizard import interview, level_for_years, main, parse_countries, parse_families

ROOT = Path(__file__).resolve().parents[1]


def test_every_role_family_makes_a_valid_profile():
    for fid in FAMILIES:
        profile = profile_from_dict(tomllib.loads(render_profile(Choices("x", ["Canada"], [fid]))))
        assert profile.family_ids == [fid]
        for domain in FAMILIES[fid]["domains"]:
            assert domain not in profile.rules.excluded_domains


@pytest.mark.parametrize("preset", sorted((ROOT / "profiles").glob("*.toml")), ids=lambda p: p.stem)
def test_shipped_presets_load(preset):
    profile = load_profile(preset)
    assert profile.families and (profile.country_codes or profile.remote == "only")


def test_years_to_level():
    assert level_for_years(0) == ("early_career", 0, 2)
    assert level_for_years(2) == ("early_career", 0, 4)
    assert level_for_years(5) == ("mid", 3, 8)
    assert level_for_years(9) == ("senior", 6, 14)
    assert level_for_years(15)[0] == "leadership"
    assert level_for_years(0, student=True) == ("student", 0, 1)


def test_parsers_are_forgiving():
    assert parse_countries("india, usa; UK") == (["India", "United States", "United Kingdom"], [])
    assert "did you mean Germany" in parse_countries("germny")[1][0]
    assert parse_families("1, marketing, Data Science") == (["software_engineering", "marketing", "data_science"], [])
    assert find("customer success") == "customer_success" and find("nonsense") == ""


def test_interactive_wizard(tmp_path):
    answers = iter(["Inda", "India", "Pune, Bangalore", "1", "1.5", "", "5, 18", "Power BI Developer", "n"])
    choices = interview(lambda _q: next(answers), say=lambda _m: None, claude_available=True)
    assert choices.countries == ["India"] and choices.cities == ["Pune", "Bangalore"]
    assert (choices.level, choices.min_years, choices.max_years) == ("early_career", 0, 4)
    assert choices.families == ["data_analytics", "finance_accounting"] and choices.extra_titles == ["Power BI Developer"]
    assert choices.ai is False


def test_flag_mode_writes_profile_and_keeps_a_backup(tmp_path):
    target = tmp_path / "profile.toml"
    target.write_text("old", encoding="utf-8")
    code = main(["--profile", str(target), "--countries", "Germany", "--years", "6", "--families", "data science",
                 "--titles", "MLOps Engineer", "--custom-family", "MLOps", "--yes", "--no-ai"])
    assert code == 0 and (tmp_path / "profile.backup.toml").read_text(encoding="utf-8") == "old"
    profile = load_profile(target)
    assert profile.family_ids == ["data_science", "mlops"] and profile.level == "mid" and profile.ai["enabled"] is False
    assert main(["--profile", str(target), "--countries", "Narnia", "--families", "1", "--yes"]) == 2


def test_my_companies_lines():
    assert parse_line("# comment") is None and parse_line("") is None and parse_line("not a url") is None
    board = parse_line("Airbnb | https://boards.greenhouse.io/airbnb   # added by me")
    assert (board.company, board.source, board.token) == ("Airbnb", "greenhouse", "airbnb")
    plain = parse_line("https://careers.example.com/jobs#open")
    assert plain.source == "generic_html" and plain.token == "https://careers.example.com/jobs#open"


def test_load_boards_reads_companies_json_and_my_companies(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "companies.json").write_text(json.dumps({"companies": [{"company": "A", "source": "lever", "token": "a"}]}), encoding="utf-8")
    (tmp_path / "my_companies.txt").write_text("https://jobs.ashbyhq.com/b\n", encoding="utf-8")
    boards, _ = load_boards(config)
    assert [(b.source, b.token) for b in boards] == [("lever", "a"), ("ashby", "b")]
    assert len(load_my_companies(tmp_path / "missing.txt")) == 0


def test_expand_boards_for_a_profile():
    boards = [
        Board("Acme", "accenture", "{keyword}"),
        Board("EY", "successfactors", "https://careers.ey.com/ey/search/?q={keyword}&locationsearch={country}", options={"max_keywords": 1}),
        Board("Jobgether", "lever", "jobgether", options={"params": {"location": "{country}"}}),
        Board("TCS", "tcs_ibegin", "{keyword}", countries=["IN"]),
        Board("Plain", "lever", "plain"),
    ]
    us = expand_boards(boards, ["US", "CA"], ["data analyst", "sql"])
    tokens = [(b.company, b.token, b.options.get("params")) for b in us]
    assert ("Acme", "data analyst", None) in tokens and ("Acme", "sql", None) in tokens
    assert ("EY", "https://careers.ey.com/ey/search/?q=data+analyst&locationsearch=United+States", None) in tokens
    assert ("Jobgether", "jobgether", {"location": "Canada"}) in tokens or any(b.options.get("params") == {"location": "Canada"} for b in us)
    assert not any(b.company == "TCS" for b in us)  # India-only site skipped for a US/Canada profile
    assert any(b.company == "TCS" for b in expand_boards(boards, ["IN"], ["analyst"]))


def test_dashboard_embeds_rows_safely():
    profile = load_profile(ROOT / "profile.toml")
    row = JobResult(company="Acme", title="Data Analyst </script><b>", experience_required="1-3 years", url="https://x/1", system_notes="",
                    category_id="data_bi", score=80, source="lever", location="Pune", matched_terms=[], retrieved_at="", is_new=True,
                    quality_tier="high_confidence")
    buckets = RunBuckets(main={"data_bi": [row]}, possible={}, overflow={})
    data = build_data(profile, buckets, [BoardHealth("Acme", "lever", "acme", "ok", 1)], {"raw_jobs": 10})
    assert data["families"][0]["rows"][0]["new"] is True and data["sources"][0]["status"] == "ok"
    html = render(data)
    assert "</script><b>" not in html and "<\\/script>" in html and "/*__DATA__*/" not in html
