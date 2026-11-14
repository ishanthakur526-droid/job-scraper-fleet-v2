from pathlib import Path

import pytest

from jobfleet import pipeline as pipeline_module
from jobfleet.classifier import Classifier
from jobfleet.http import FetchError
from jobfleet.models import Board, RawJob
from jobfleet.pipeline import JobPipeline, dedupe_raw
from jobfleet.profile import load_profile

PROFILE = Path(__file__).resolve().parents[1] / "profile.toml"
DESC = "Bengaluru. SQL dashboards, Excel reporting, analytics insights. 1-3 years of experience."


@pytest.fixture(scope="module")
def classifier():
    return Classifier.from_profile(load_profile(PROFILE))


def raw(title, company="Acme", url=None, source="lever", location="Bengaluru, India", key="", **kw):
    url = url or f"https://example.com/{company}/{title}/{key}".replace(" ", "-")
    return RawJob(company=company, title=title, location=location, url=url, description=kw.pop("description", DESC), source=source, stable_key=key, **kw)


def test_category_cap_moves_extra_rows_to_overflow_instead_of_dropping(classifier):
    jobs = [raw(f"Data Analyst {letter}", company=f"Co{c}", key=f"k{c}{letter}") for c in range(6) for letter in "abcdefghij"]
    pipeline = JobPipeline(http=None, classifier=classifier, max_per_category=40, per_company_cap=8)
    buckets = pipeline.build(pipeline.evaluate(jobs))
    main, overflow = buckets.main["data_bi"], buckets.overflow["data_bi"]
    assert len(main) == 40 and len(main) + len(overflow) == 60
    per_company = {}
    for row in main:
        per_company[row.company] = per_company.get(row.company, 0) + 1
    assert max(per_company.values()) <= 8
    assert len(buckets.recorded()) == 60  # every accepted job is persisted


def test_identical_requisitions_collapse_into_one_row(classifier):
    jobs = [raw("Business Analyst, ROC, ROC", company="Amazon", source="amazon_jobs", key=f"amazon_jobs:{n}", location="Hyderabad, Telangana, IND", url=f"https://www.amazon.jobs/en/jobs/{n}/x") for n in (1, 2, 3)]
    pipeline = JobPipeline(http=None, classifier=classifier)
    rows = pipeline.build(pipeline.evaluate(jobs)).main["data_bi"]
    assert len(rows) == 1
    assert len(rows[0].group_keys) == 2 and "+2 more" in rows[0].system_notes


def test_cross_source_duplicates_collapse(classifier):
    jobs = [
        raw("Business Data Analyst", company="Accenture", source="accenture", key="accenture:1", location="Bengaluru"),
        raw("Business Data Analyst", company="Accenture", source="workday", key="workday:accenture:1", location="Bengaluru, India"),
    ]
    pipeline = JobPipeline(http=None, classifier=classifier)
    rows = pipeline.build(pipeline.evaluate(jobs)).main["data_bi"]
    assert len(rows) == 1 and len(rows[0].group_keys) == 1


def test_same_requisition_on_two_sites_is_deduped_by_stable_key():
    jobs = [raw("Analyst", key="workday:erm:r1", url="https://erm/a"), raw("Analyst", key="workday:erm:r1", url="https://erm/b", description="longer " * 50)]
    kept = dedupe_raw(jobs)
    assert len(kept) == 1 and kept[0].url == "https://erm/b"


def test_routes_and_prefilter_audit(classifier):
    jobs = [
        raw("Data Analyst", flags={"aggregator": True}, key="a"),
        raw("Financial Analyst", key="b", description="Mumbai. FP&A forecasting in Excel. 1-2 years of experience."),
        raw("Welder", flags={"prefilter": "irrelevant_title"}, key="c"),
    ]
    pipeline = JobPipeline(http=None, classifier=classifier)
    buckets = pipeline.build(pipeline.evaluate(jobs))
    assert [r.key for r in buckets.aggregator] == ["a"]
    assert [r.key for r in buckets.adjacent] == ["b"]
    assert buckets.rejected[0].stage == "prefilter" and buckets.rejected[0].reason == "prefilter:irrelevant_title"


class _Adapter:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.partial = False
        self.notes = []

    def list_jobs(self, board):
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return self.behaviour


def test_collection_isolates_board_failures_and_skips_quarantined(classifier, monkeypatch):
    behaviours = {
        "ok": [raw("Data Analyst", key="x")],
        "dead": FetchError("HTTP 404", status=404, hard=True),
        "bug": KeyError("unexpected"),
    }
    calls = []

    def fake_adapter_for(source, http, context=None):
        calls.append(source)
        return _Adapter(behaviours[source])

    monkeypatch.setattr(pipeline_module, "adapter_for", fake_adapter_for)
    boards = [Board("A", "ok", "t"), Board("B", "dead", "t"), Board("C", "bug", "t"), Board("D", "ok", "q")]
    pipeline = JobPipeline(http=None, classifier=classifier, workers=4)
    jobs, health = pipeline.collect_from_boards(boards, quarantined={boards[3].key: "2026-12-01T00:00:00+00:00"})
    statuses = [(h.company, h.status, h.hard_failure) for h in health]
    assert statuses == [("A", "ok", False), ("B", "failed", True), ("C", "failed", False), ("D", "quarantined", False)]
    assert len(jobs) == 1 and jobs[0].board_key == boards[0].key
    assert calls.count("ok") == 1


def test_multi_location_jobs_show_the_indian_office_first(classifier):
    job = raw("Accounts Receivable Analyst", location="Colombo, Sri Lanka", locations=["IND-Bangalore-A, RMZ Infinity"], country_codes=["Sri Lanka"], key="workday:lseg:r1")
    rows = JobPipeline(http=None, classifier=classifier).build(JobPipeline(http=None, classifier=classifier).evaluate([job])).main["excel_mis"]
    assert rows[0].location == "IND-Bangalore-A, RMZ Infinity (also Colombo, Sri Lanka)"
