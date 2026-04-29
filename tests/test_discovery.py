import unittest
from unittest.mock import patch

from jobfleet.board_discovery import DiscoverySettings, _verify_board
from jobfleet.discovery import _dedupe, _extract_ats_urls
from jobfleet.models import Board, Category, RawJob
from jobfleet.sources.ats import board_from_url


class FakeAdapter:
    def __init__(self, jobs):
        self.jobs = jobs

    def list_jobs(self, board):
        return self.jobs


class DiscoveryTests(unittest.TestCase):
    def test_board_from_url_parses_ats_tokens(self):
        self.assertEqual(board_from_url("https://jobs.lever.co/example/abc").token, "example")
        self.assertEqual(board_from_url("https://boards.greenhouse.io/example/jobs/123").token, "example")
        self.assertEqual(board_from_url("https://jobs.ashbyhq.com/example/abc").token, "example")
        self.assertEqual(board_from_url("https://careers.smartrecruiters.com/Freshworks").token, "Freshworks")
        self.assertEqual(
            board_from_url("https://workday.wd5.myworkdayjobs.com/en-US/Workday").token,
            "workday.wd5.myworkdayjobs.com|workday|Workday",
        )

    def test_dedupe_normalizes_trailing_punctuation(self):
        urls = _dedupe(["https://jobs.lever.co/example/abc,", "https://jobs.lever.co/example/abc"])
        self.assertEqual(urls, ["https://jobs.lever.co/example/abc"])

    def test_extract_ats_urls_from_html(self):
        html = '<a href="/l/?uddg=https%3A%2F%2Fjobs.lever.co%2Fexample%2Fabc">result</a>'
        self.assertEqual(_extract_ats_urls(html), ["https://jobs.lever.co/example/abc"])


class BoardVerificationTests(unittest.TestCase):
    def settings(self):
        return DiscoverySettings(
            enabled_by_default=True,
            max_queries=1,
            results_per_query=1,
            max_generated_candidates=1,
            min_total_jobs=1,
            min_india_jobs=1,
            target_companies=[],
            target_queries=[],
        )

    def categories(self):
        return [
            Category(
                id="data_bi",
                name="Data & BI",
                output="data_bi_roles_today.csv",
                target_roles=["Data Analyst"],
                positive_keywords=["sql", "dashboard"],
            )
        ]

    def test_board_verification_rejects_india_jobs_without_category_hits(self):
        jobs = [
            RawJob(
                company="Example",
                title="Customer Support Specialist",
                location="Bengaluru, India",
                url="https://example.com/job/1",
                description="Support customer operations.",
                source="smartrecruiters",
            )
        ]

        with patch("jobfleet.board_discovery.adapter_for", return_value=FakeAdapter(jobs)):
            row = _verify_board(None, Board("Example", "smartrecruiters", "example"), self.categories(), self.settings())

        self.assertEqual(row["status"], "rejected_no_category_match")

    def test_board_verification_accepts_india_jobs_with_category_hits(self):
        jobs = [
            RawJob(
                company="Example",
                title="Data Analyst",
                location="Bengaluru, India",
                url="https://example.com/job/2",
                description="Build SQL dashboards for business teams.",
                source="smartrecruiters",
            )
        ]

        with patch("jobfleet.board_discovery.adapter_for", return_value=FakeAdapter(jobs)):
            row = _verify_board(None, Board("Example", "smartrecruiters", "example"), self.categories(), self.settings())

        self.assertEqual(row["status"], "accepted")
        self.assertEqual(row["priority_categories"], "data_bi")


if __name__ == "__main__":
    unittest.main()
