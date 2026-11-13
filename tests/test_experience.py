import pytest

from jobfleet.experience import parse_experience


@pytest.mark.parametrize(
    "text",
    [
        "FactSet has been a leader for over 45 years. Join our team.",  # defect: rejected a Hyderabad analyst role
        "ERM has over 50 years of experience helping clients. You will support analysts.",
        "With 100+ years of history, we are hiring.",  # '00+' used to be read inside '100+'
        "Candidates aged 18-35 years are welcome.",
        "This is a 2 year contract role.",
        "Build dashboards and partner with business teams.",
    ],
)
def test_non_requirements_are_unspecified(text):
    result = parse_experience(text)
    assert result.decision == "accept"
    assert result.min_years is None


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Requires 2-5 years of analytics experience.", "2-5 years"),
        ("3+ years of experience with SQL required.", "3+ years"),
        ("1.5+ years of experience in analytics.", "1.5+ years"),  # used to parse as 5+
        ("two to four years of relevant experience", "2-4 years"),
        ("6-12 months of experience in reporting", "6-12 months"),
        ("Experience: 1-3 Yrs", "1-3 years"),
        ("Risk Analyst | Exp - 1 to 3 Yrs", "1-3 years"),
        ("We are looking for candidates with 2+ years of experience", "2+ years"),
        ("more than 2 years of experience in finance", "over 2 years"),
    ],
)
def test_allowed_requirements(text, label):
    result = parse_experience(text)
    assert result.decision == "accept"
    assert result.label == label


@pytest.mark.parametrize(
    "text",
    [
        "Minimum 4 years of market research experience required.",
        "Minimum of five (5) years of professional experience",
        "over 3 years of experience in finance",
        "8+ years of experience leading analytics teams.",
    ],
)
def test_rejected_requirements(text):
    assert parse_experience(text).decision == "reject"


def test_overall_vs_tool_experience_needs_review():
    result = parse_experience("5+ years of experience overall. 2+ years of experience with SQL.")
    assert result.decision == "review"


def test_degree_alternatives_take_the_easier_path():
    text = "Bachelor's degree with 5+ years of experience or Master's degree with 3+ years of experience."
    assert parse_experience(text).decision == "accept"


def test_preferred_qualifications_never_reject():
    text = "Preferred Qualifications:\n- 5+ years of experience in banking\n- Strong Excel skills"
    result = parse_experience(text)
    assert result.decision == "accept"
    assert result.label.startswith("Preferred")
    amazon_style = parse_experience("- 2+ years of experience in analytics", preferred_text="- 5+ years of experience in banking")
    assert amazon_style.decision == "accept" and amazon_style.label == "2+ years"


def test_preferred_section_does_not_end_at_plain_bullets():
    text = "Preferred qualifications:\n- strong excel skills\n- 6+ years of experience in banking"
    assert parse_experience(text).decision == "accept"


def test_fresher_signal():
    result = parse_experience("Freshers can apply. Good communication skills.")
    assert result.decision == "accept" and result.min_years == 0


def test_internal_mobility_rules_are_ignored():
    text = "Internal candidates must have completed minimum 18 months in current role. 5+ years of experience in analytics."
    assert parse_experience(text).decision == "reject"
    assert parse_experience("Minimum 18 months in current role before applying.").min_years is None


def test_title_mentions_count_as_requirements():
    assert parse_experience("Market research.", title="MI | 6 to 12 Years | Hyderabad").decision == "reject"
    assert parse_experience("SQL.", title="Risk Analyst | Exp - 1 to 3 Yrs").label == "1-3 years"
