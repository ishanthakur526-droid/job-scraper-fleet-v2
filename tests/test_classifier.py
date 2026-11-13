from pathlib import Path

import pytest

from jobfleet.classifier import Classifier
from jobfleet.models import RawJob
from jobfleet.profile import load_profile
from jobfleet.text import keyword_hits

PROFILE = Path(__file__).resolve().parents[1] / "profile.toml"


@pytest.fixture(scope="module")
def classifier():
    return Classifier.from_profile(load_profile(PROFILE))


def job(title, description="Bengaluru role. Build SQL dashboards and Excel reporting for analytics insights.", location="Bengaluru, India", **kw):
    return RawJob(company=kw.pop("company", "Example"), title=title, location=location, url=kw.pop("url", "https://example.com/j/1"), description=description, source=kw.pop("source", "test"), **kw)


def test_description_words_no_longer_trigger_negative_keywords(classifier):
    # v2 rejected these: 'Active Directory', 'report to the Director', 'principal responsibilities', 'staffing'
    text = (
        "Principal responsibilities: build SQL dashboards and Excel reporting. You will report to the Director of Analytics. "
        "Experience with Active Directory is a plus. We partner with staffing teams. 1-3 years of experience."
    )
    result = classifier.evaluate(job("Business Analyst", text))
    assert result.decision == "accept", result.reason


@pytest.mark.parametrize("word", ["excellent", "mission", "commission", "marketing", "pivotal", "diversity, equity and inclusion"])
def test_substring_keywords_do_not_score(word):
    assert keyword_hits(f"We value {word} people.", ["excel", "mis", "market", "pivot", "equity"]) == []


def test_real_keywords_still_score():
    assert keyword_hits("Advanced Excel, MIS reports, pivot tables, equity research", ["excel", "mis", "pivot", "equity"]) == ["excel", "mis", "pivot", "equity"]


def test_reordered_two_word_title_matches(classifier):
    result = classifier.evaluate(job("Analyst, Data"))
    assert result.decision == "accept" and result.category_id == "data_bi"


@pytest.mark.parametrize(
    "title",
    [
        "Associate Security Operations Analyst - 11953",
        "Security Operations Analyst (L1) - MS- Defender",
        "Endpoint Operations Analyst (L1) - Intune & SCCM",
        "Talent Acquisition & Operations Specialist",
        "Support Operations Specialist (Night Shift)",
        "Software Development Engineer - Analytics Platform",
    ],
)
def test_it_and_engineering_operations_titles_are_excluded(classifier, title):
    result = classifier.evaluate(job(title))
    assert result.decision == "reject"
    assert result.reason.startswith("non_target_title")


def test_bi_engineer_is_in_scope(classifier):
    result = classifier.evaluate(job("Business Intelligence Engineer I, Amazon Pay", "Hyderabad. SQL, dashboards, reporting. 1+ years of experience."))
    assert result.decision == "accept" and result.category_id == "data_bi"


@pytest.mark.parametrize(
    "title",
    ["Trainee, Domain Analytics", "Apprentice Research Analyst - Campus", "Graduate Data Analyst", "Data Analyst Intern", "Business Analyst Internship"],
)
def test_entry_programme_titles_are_excluded(classifier, title):
    result = classifier.evaluate(job(title))
    assert result.decision == "reject" and result.reason.startswith("excluded_entry_title")


def test_internal_audit_is_not_an_internship(classifier):
    assert classifier.title_gate("Internal Audit Analyst").status == "ok"
    assert classifier.title_gate("International Business Analyst").status == "ok"


def test_amazon_flags(classifier):
    assert classifier.evaluate(job("Business Analyst", flags={"intern": True})).reason.startswith("excluded_entry_title")
    assert classifier.evaluate(job("Business Analyst", flags={"people_manager": True})).reason.startswith("excluded_seniority")


def test_lead_generation_and_staff_accountant_are_not_seniority(classifier):
    assert classifier.title_gate("Lead Generation Executive").status == "ok"
    assert classifier.title_gate("Associate Staff Accountant").status == "ok"
    assert classifier.title_gate("Team Lead - MIS").status == "reject"


def test_senior_analyst_needs_explicit_low_experience(classifier):
    kept = classifier.evaluate(job("Senior Data Analyst", "Mumbai. SQL dashboards. 2-5 years of experience required."))
    assert kept.decision == "accept" and kept.tier == "needs_review" and "senior_title" in kept.review_flags
    dropped = classifier.evaluate(job("Senior Data Analyst", "Mumbai. SQL dashboards and reporting."))
    assert dropped.decision == "reject" and dropped.reason.startswith("conditional_title_unverified")
    assert classifier.evaluate(job("Senior Manager, Analytics")).reason.startswith("excluded_seniority")


def test_junior_manager_rule(classifier):
    kept = classifier.evaluate(job("Assistant Manager - MIS", "Pune. Advanced Excel, MIS reporting, VBA. 2-4 years of experience."))
    assert kept.decision == "accept" and kept.category_id == "excel_mis" and kept.tier == "needs_review"
    assert classifier.evaluate(job("Assistant Manager - MIS", "Pune. Advanced Excel, MIS reporting.")).decision == "reject"
    assert classifier.evaluate(job("Manager - MIS", "2-4 years of experience")).reason.startswith("excluded_seniority")


def test_level_three_titles_need_explicit_experience(classifier):
    assert classifier.evaluate(job("Business Analyst III", "SQL dashboards. 3+ years of experience required.")).decision == "accept"
    assert classifier.evaluate(job("Business Analyst III", "SQL dashboards and reporting.")).decision == "reject"


def test_adjacent_and_aggregator_routes(classifier):
    adjacent = classifier.evaluate(job("Financial Analyst (FP&A)", "Mumbai. FP&A, forecasting, Excel. 1-3 years of experience."))
    assert adjacent.decision == "accept" and adjacent.route == "adjacent"
    aggregated = classifier.evaluate(job("Data Analyst", flags={"aggregator": True}))
    assert aggregated.decision == "accept" and aggregated.route == "aggregator"


def test_indiana_job_is_rejected_as_non_india(classifier):
    result = classifier.evaluate(job("Data Analyst", location="Indianapolis, Indiana"))
    assert result.decision == "reject" and result.reason == "non_india"


def test_unknown_location_rejected_unless_inferred(classifier):
    assert classifier.evaluate(job("Data Analyst", "SQL dashboards.", location="2 Locations")).reason == "geo_unknown"
    inferred = classifier.evaluate(job("Data Analyst", "This role is based in Pune, India. SQL dashboards and reporting.", location="Remote"))
    assert inferred.decision == "accept" and "inferred_location" in inferred.review_flags


def test_experience_too_high(classifier):
    result = classifier.evaluate(job("Data Analyst", "Bengaluru. SQL. Minimum 5 years of experience required."))
    assert result.reason == "experience_too_high"


def test_category_tie_prefers_research(classifier):
    result = classifier.evaluate(job("Research Analyst - Data Operations", "Market research, Excel reporting and dashboards."))
    assert result.category_id == "research"


def test_borderline_titles_become_possible_matches(classifier):
    result = classifier.evaluate(job("Associate - Customer Insights", "Bengaluru. Analytics reporting."))
    assert result.decision == "possible" and result.tier == "possible_match"


def test_prefilter_skips_detail_fetch_for_irrelevant_titles(classifier):
    assert classifier.prefilter("Senior Software Engineer")[0] is False
    assert classifier.prefilter("Chef de Partie")[0] is False
    assert classifier.prefilter("Business Analyst")[0] is True
    assert classifier.prefilter("Assistant Manager - Data Analytics")[0] is True


# ---- regressions found in the first live v3 run (2026-11-13) ----
@pytest.mark.parametrize(
    "title",
    [
        "LMTS Agentic AP/Invoicing",  # Salesforce engineering level, matched 'Accounts Payable'
        "TL-AR Management HC",  # team lead
        "Service Delivery Leader - F&A - AP 3",
        "Business Systems Analyst, ServiceNow",
        "Senior Information Security Risk Analyst",
        "Security Analyst - Risk Management",
        "Operations Specialist - SAP Integration, Event Mesh & AI",
        "Assistant Manager - Business Finance | CA pass-out 2026",
    ],
)
def test_live_run_false_positives_are_excluded(classifier, title):
    assert classifier.evaluate(job(title, "Hyderabad. Excel, MIS reporting, accounts payable. 1-3 years of experience.")).decision == "reject"


def test_title_experience_is_a_requirement(classifier):
    capgemini = classifier.evaluate(job("MI (Market Intelligence) | 6 to 12 Years | Hyderabad and Bangalore", "Market research. 2-5 years preferred."))
    assert capgemini.reason == "experience_too_high"
    paytm = classifier.evaluate(job("Business Analytics- Paytm Gold | Experience : 5-7 yrs", "SQL dashboards."))
    assert paytm.reason == "experience_too_high"


def test_generic_associate_analyst_needs_a_data_word(classifier):
    tax = classifier.evaluate(job("Associate Analyst - TAX - National - TAX - Indirect Tax - Core - Mumbai", "Excel reporting and analysis of tax data."))
    assert not (tax.decision == "accept" and tax.category_id == "data_bi")
    metrics = classifier.evaluate(job("Associate Analyst, Analytics & Metrics", "Mumbai. SQL dashboards, Excel reporting. 1-3 years."))
    assert metrics.decision == "accept" and metrics.category_id == "data_bi"


def test_loose_token_matches_are_rejected(classifier):
    title = "Sr. Compliance Associate-Quality Analyst, Global Solutions Risk & Compliance"
    result = classifier.evaluate(job(title, "Pune. Excel. 1+ years of experience."))
    assert not (result.decision == "accept" and result.route == "adjacent")


@pytest.mark.parametrize(
    ("title", "excluded"),
    [
        ("Web Operations Quality Analyst", True),
        ("Analyst, Business Partner Solutions, HR Team", True),
        ("Marketing Technology Operations Specialist", True),
        ("Data Quality Analyst", False),
        ("HR Analytics Analyst", False),
    ],
)
def test_eval_set_false_positive_patterns(classifier, title, excluded):
    assert bool(classifier.non_target(classifier.title_gate(title).norm)) is excluded
