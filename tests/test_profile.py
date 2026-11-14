from pathlib import Path

import pytest

from jobfleet.classifier import Classifier
from jobfleet.experience import parse_experience
from jobfleet.levels import DOMAINS
from jobfleet.profile import ProfileError, load_profile, profile_from_dict
from jobfleet.scout import fill_template
from jobfleet.triage import build_prompt, triage_schema

ROOT = Path(__file__).resolve().parents[1]


def minimal(**overrides):
    data = {
        "location": {"countries": ["United States"]},
        "experience": {"level": "mid", "min_years": 3, "max_years": 7},
        "role_family": [{"name": "Software Engineering", "titles": ["Software Engineer", "Backend Engineer"], "domains": ["engineering"]}],
    }
    data.update(overrides)
    return data


def test_shipped_profile_pins_the_v3_rules():
    profile = load_profile(ROOT / "profile.toml")
    rules = profile.rules
    assert profile.family_ids == ["data_bi", "research", "excel_mis"] and profile.adjacent.output == "adjacent_roles_today.csv"
    assert (profile.min_years, profile.max_years, profile.countries) == (0, 3, ["India"])
    assert rules.level_actions["intern"] == rules.level_actions["entry_program"] == "exclude"
    assert rules.level_actions["senior"] == rules.level_actions["junior_manager"] == "conditional"
    assert all(rules.level_actions[n] == "exclude" for n in ("vp", "director", "chief", "principal", "head", "architect", "lead", "staff", "manager"))
    assert rules.senior_only_for == ("analyst", "associate", "executive")
    assert set(rules.excluded_domains) == set(DOMAINS)  # the analyst profile owns no excluded domain
    assert rules.tie_priority["research"] > rules.tie_priority["excel_mis"] > rules.tie_priority["data_bi"] > rules.tie_priority["adjacent"]
    assert list(rules.abbreviations)[:7] == ["sr", "jr", "assoc", "exec", "mgr", "ops", "bie"]  # 'bie' must expand before 'bi'


@pytest.mark.parametrize(
    "change, message",
    [
        ({"location": {"countries": []}}, "countries is empty"),
        ({"experience": {"level": "expert"}}, "level must be one of"),
        ({"experience": {"min_years": 5, "max_years": 2}}, "larger than max_years"),
        ({"experience": {"min_years": "five"}}, "should be a number"),
        ({"role_family": []}, "at least one [[role_family]]"),
        ({"role_family": [{"name": "X", "titles": []}]}, "needs at least one job title"),
        ({"role_family": [{"name": "X", "titles": ["A"], "domains": ["enginering"]}]}, "Unknown domain 'enginering'"),
        ({"advanced": {"exclude_levels": ["seniors"]}}, "unknown level 'seniors'"),
        ({"advanced": {"tie_priority": ["nope"]}}, "tie_priority mentions 'nope'"),
        ({"location": {"countries": ["India"], "remote": "sometimes"}}, "remote must be one of"),
    ],
)
def test_profile_errors_are_friendly(change, message):
    with pytest.raises(ProfileError) as info:
        profile_from_dict(minimal(**change))
    assert message in str(info.value)


def test_toml_syntax_error_is_explained(tmp_path):
    path = tmp_path / "profile.toml"
    path.write_text('name = "x\n', encoding="utf-8")
    with pytest.raises(ProfileError, match="formatting mistake"):
        load_profile(path)
    with pytest.raises(ProfileError, match="Setup.bat"):
        load_profile(tmp_path / "missing.toml")


def test_defaults_are_derived_from_titles():
    profile = profile_from_dict(minimal())
    assert profile.family_ids == ["software_engineering"]
    assert profile.families[0].output == "software_engineering_jobs_today.csv"
    assert "engineering" not in profile.rules.excluded_domains and "sales" in profile.rules.excluded_domains
    assert {"software", "backend", "engineer"} <= profile.rules.prefilter_terms
    assert profile.search_keywords == ["software engineer", "backend engineer"]
    assert profile.ai["triage"]["demote_confidence"] == 0.85


def test_mid_level_engineer_profile_gate():
    classifier = Classifier.from_profile(profile_from_dict(minimal()))
    assert classifier.title_gate("Senior Software Engineer").status == "ok"
    assert classifier.non_target(classifier.title_gate("Senior Software Engineer").norm) == ""
    assert classifier.title_gate("Software Development Manager").reason == "excluded_seniority:manager"
    assert classifier.title_gate("Lead Software Engineer").status == "conditional"  # lead: needs a stated range
    assert classifier.title_gate("Principal Engineer").reason == "excluded_seniority:principal"
    assert classifier.title_gate("Software Engineer Intern").reason == "excluded_entry_title:intern"
    assert classifier.title_gate("Graduate Software Engineer").reason == "excluded_entry_title:graduate"
    assert classifier.non_target(classifier.title_gate("Account Executive").norm) == "sales"


def test_level_words_inside_a_wanted_title_are_exempt():
    data = minimal(
        experience={"level": "early_career", "max_years": 3},
        role_family=[{"name": "Product", "titles": ["Product Manager", "Product Owner"]}],
    )
    classifier = Classifier.from_profile(profile_from_dict(data))
    assert classifier.title_gate("Product Manager").status == "ok"
    assert classifier.title_gate("Associate Product Manager").status == "ok"  # an entry-level product title
    assert classifier.title_gate("Assistant Manager - Product").status == "conditional"  # junior_manager outside the wanted title
    assert classifier.title_gate("Engineering Manager").reason == "excluded_seniority:manager"
    assert classifier.title_gate("Senior Product Manager").status == "conditional"


def test_student_profile_keeps_internships():
    data = minimal(experience={"level": "student"}, role_family=[{"name": "Data", "titles": ["Data Analyst"]}])
    classifier = Classifier.from_profile(profile_from_dict(data))
    assert classifier.title_gate("Data Analyst Intern").status == "ok"
    assert classifier.title_gate("Graduate Data Analyst").status == "ok"
    assert classifier.title_gate("Senior Data Analyst").reason == "excluded_seniority:senior"


def test_experience_range_is_configurable():
    assert parse_experience("You have 5+ years of experience in SQL.", max_years=7).decision == "accept"
    assert parse_experience("You have 9+ years of experience in SQL.", max_years=7).decision == "reject"
    too_low = parse_experience("0-2 years of experience required.", min_years=5, max_years=10)
    assert too_low.decision == "reject" and too_low.reason == "experience_too_low"
    assert parse_experience("1+ years of experience required.", min_years=5, max_years=10).reason == "experience_too_low"
    assert parse_experience("3+ years of experience required.", min_years=5, max_years=10).decision == "accept"
    assert parse_experience("Freshers welcome.", min_years=5, max_years=10).reason == "experience_too_low"
    assert parse_experience("Freshers welcome.").decision == "accept"
    assert parse_experience("You bring 20+ years of experience leading teams.", min_years=10, max_years=30).decision == "accept"
    assert parse_experience("You bring 20+ years of experience leading teams.").min_years is None  # not credible at 0-3


def test_claude_prompts_follow_the_profile():
    profile = profile_from_dict(minimal())
    prompt = build_prompt(profile, profile.family_ids)
    assert "United States or remote" in prompt and "3-7 years" in prompt and "Software Engineer, Backend Engineer" in prompt
    assert triage_schema(profile.family_ids)["properties"]["verdicts"]["items"]["properties"]["category"]["enum"] == [
        "software_engineering", "adjacent", "none"
    ]
    template = (ROOT / "config" / "company_scout_prompt.md").read_text(encoding="utf-8")
    filled = fill_template(template, profile)
    assert "{{" not in filled and "United States" in filled and "software_engineering" in filled
