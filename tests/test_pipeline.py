import unittest

from jobfleet.models import Category, RawJob
from jobfleet.pipeline import JobPipeline


def categories():
    return [
        Category(
            id="data_bi",
            name="Data & BI",
            output="data_bi_roles_today.csv",
            target_roles=["Data Analyst", "Operations Analyst"],
            positive_keywords=["excel", "reporting", "analytics", "insights"],
        ),
        Category(
            id="research",
            name="Research",
            output="research_roles_today.csv",
            target_roles=["Research Analyst"],
            positive_keywords=["research", "market"],
        ),
        Category(
            id="excel_mis",
            name="Excel / MIS",
            output="excel_sheets_roles_today.csv",
            target_roles=["Data Operations Analyst", "Operations Analyst"],
            positive_keywords=["excel", "mis", "reporting"],
        ),
    ]


def raw_job(title: str, description: str = "India based role. Excel reporting analytics research market.") -> RawJob:
    return RawJob(
        company="Example",
        title=title,
        location="Bangalore, India",
        url="https://example.com/job/1",
        description=description,
        source="test",
    )


class PipelineClassificationTests(unittest.TestCase):
    def test_job_is_assigned_to_only_one_category(self):
        pipeline = JobPipeline(http=None)
        buckets = pipeline.classify([raw_job("Research Analyst --Data Operations")], categories(), 25)
        total = sum(len(items) for items in buckets.values())

        self.assertEqual(total, 1)
        self.assertEqual(len(buckets["research"]), 1)

    def test_tie_prefers_excel_mis_over_broad_data_bi(self):
        pipeline = JobPipeline(http=None)
        buckets = pipeline.classify([raw_job("Operations Analyst", "India based role. Excel reporting.")], categories(), 25)
        total = sum(len(items) for items in buckets.values())

        self.assertEqual(total, 1)
        self.assertEqual(len(buckets["excel_mis"]), 1)

    def test_false_negative_layer_keeps_borderline_jobs_out_of_main_csv(self):
        pipeline = JobPipeline(http=None)
        job = raw_job("Associate - Customer Insights", "India based role. Analytics reporting.")
        buckets = pipeline.classify([job], categories(), 25)
        possible, rejected = pipeline.discover_false_negatives([job], categories(), buckets)

        self.assertEqual(sum(len(items) for items in buckets.values()), 0)
        self.assertGreaterEqual(sum(len(items) for items in possible.values()), 1)
        self.assertEqual(rejected[0].reason, "weak_role_match")

    def test_non_india_rejection_is_audited_not_possible(self):
        pipeline = JobPipeline(http=None)
        job = RawJob(
            company="Example",
            title="Data Analyst",
            location="London, United Kingdom",
            url="https://example.com/job/2",
            description="Analytics reporting role.",
            source="test",
        )
        buckets = pipeline.classify([job], categories(), 25)
        possible, rejected = pipeline.discover_false_negatives([job], categories(), buckets)

        self.assertEqual(sum(len(items) for items in possible.values()), 0)
        self.assertEqual(rejected[0].reason, "non_india")

    def test_possible_match_excludes_engineering_titles(self):
        pipeline = JobPipeline(http=None)
        job = raw_job("Software Development Engineer - Analytics Platform", "India based role. Analytics reporting.")
        buckets = pipeline.classify([job], categories(), 25)
        possible, rejected = pipeline.discover_false_negatives([job], categories(), buckets)

        self.assertEqual(sum(len(items) for items in possible.values()), 0)
        self.assertEqual(rejected[0].reason, "weak_role_match")


if __name__ == "__main__":
    unittest.main()
