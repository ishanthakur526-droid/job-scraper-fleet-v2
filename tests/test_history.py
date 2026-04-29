import unittest
import uuid
from pathlib import Path

from jobfleet.history import mark_new_jobs
from jobfleet.models import JobResult


def result(url: str) -> JobResult:
    return JobResult(
        company="Example",
        title="Data Analyst",
        experience_required="Unspecified",
        url=url,
        system_notes="",
        category_id="data_bi",
        score=80,
        source="test",
        location="India",
        matched_terms=["Data Analyst"],
        retrieved_at="2026-04-28T00:00:00+00:00",
        quality_tier="high_confidence",
    )


class HistoryTests(unittest.TestCase):
    def test_marks_only_first_seen_as_new(self):
        state_dir = Path.cwd() / "job_scraper_fleet_v2" / ".test_tmp" / str(uuid.uuid4())
        state_dir.mkdir(parents=True, exist_ok=True)
        first = mark_new_jobs(state_dir, {"data_bi": [result("https://example.com/job/1")]})
        second = mark_new_jobs(state_dir, {"data_bi": [result("https://example.com/job/1")]})

        self.assertEqual(len(first["data_bi"]), 1)
        self.assertEqual(len(second["data_bi"]), 0)
        self.assertTrue((state_dir / "job_history.csv").exists())

    def test_marks_missing_jobs_in_history(self):
        state_dir = Path.cwd() / "job_scraper_fleet_v2" / ".test_tmp" / str(uuid.uuid4())
        state_dir.mkdir(parents=True, exist_ok=True)
        mark_new_jobs(state_dir, {"data_bi": [result("https://example.com/job/1")]})
        mark_new_jobs(state_dir, {"data_bi": []})

        missing = (state_dir / "expired_or_missing_jobs.csv").read_text(encoding="utf-8")
        self.assertIn("https://example.com/job/1", missing)
        self.assertIn(",no,", missing)


if __name__ == "__main__":
    unittest.main()
