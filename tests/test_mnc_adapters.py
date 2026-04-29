import unittest

from jobfleet.models import Board
from jobfleet.sources.ats import adapter_for


class FakeHttp:
    def __init__(self, text=None, json_data=None, post_data=None):
        self.text = text or {}
        self.json_data = json_data or {}
        self.post_data = post_data or {}

    def get_text(self, url, accept="text/html,application/json"):
        if url not in self.text:
            raise AssertionError(f"Unexpected text URL: {url}")
        return self.text[url]

    def get_json(self, url):
        if url not in self.json_data:
            raise AssertionError(f"Unexpected JSON URL: {url}")
        return self.json_data[url]

    def post_json(self, url, payload, headers=None):
        if url not in self.post_data:
            raise AssertionError(f"Unexpected POST URL: {url}")
        return self.post_data[url]

    def post_form(self, url, payload, headers=None):
        if url not in self.post_data:
            raise AssertionError(f"Unexpected POST URL: {url}")
        return self.post_data[url]


class MncAdapterTests(unittest.TestCase):
    def test_amazon_adapter_maps_search_json(self):
        url = "https://www.amazon.jobs/en/search.json?base_query=analyst&country=IND&offset=0&result_limit=10"
        http = FakeHttp(
            json_data={
                url: {
                    "jobs": [
                        {
                            "id": "123",
                            "title": "Finance Analyst",
                            "city": "Hyderabad",
                            "country_code": "IND",
                            "description": "Use Excel and dashboards.",
                            "basic_qualifications": "2+ years experience",
                        }
                    ]
                },
                url.replace("offset=0", "offset=10"): {"jobs": []},
            }
        )

        jobs = list(adapter_for("amazon_jobs", http).list_jobs(Board("Amazon", "amazon_jobs", "analyst")))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Finance Analyst")
        self.assertIn("Hyderabad", jobs[0].location)

    def test_capgemini_adapter_maps_jobstream_json(self):
        url = "https://cg-jobstream-api.azurewebsites.net/api/job-search?page=1&size=50&country_code=in-en&search=analyst"
        http = FakeHttp(
            json_data={
                url: {
                    "data": [
                        {
                            "id": "abc",
                            "title": "Business Analyst",
                            "location": "Pune, Bangalore",
                            "apply_job_url": "https://careers.capgemini.com/job/abc",
                            "description": "SQL and data analysis.",
                        }
                    ]
                },
                url.replace("page=1", "page=2"): {"data": []},
            }
        )

        jobs = list(adapter_for("capgemini", http).list_jobs(Board("Capgemini", "capgemini", "analyst")))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].url, "https://careers.capgemini.com/job/abc")
        self.assertIn("SQL", jobs[0].description)

    def test_accenture_adapter_maps_findjobs_json(self):
        http = FakeHttp(
            post_data={
                "https://www.accenture.com/api/accenture/elastic/findjobs": {
                    "data": [
                        {
                            "requisitionId": "ATCI-123",
                            "title": "Business Data Analyst",
                            "jobDetailUrl": "https://www.accenture.com/{0}/careers/jobdetails?id=ATCI-123",
                            "jobDescriptionClean": "Build dashboards and analyze business performance.",
                            "location": ["Bengaluru"],
                            "mustHaveSkills": ["Power BI", "SQL"],
                            "updateDate": "2026-04-28T10:10:28.339-07:00",
                        }
                    ]
                }
            }
        )

        jobs = list(adapter_for("accenture", http).list_jobs(Board("Accenture", "accenture", "analyst")))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_id, "ATCI-123")
        self.assertEqual(jobs[0].url, "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-123")
        self.assertIn("Power BI", jobs[0].description)
        self.assertEqual(jobs[0].location, "Bengaluru")

    def test_tcs_adapter_maps_ibegin_json(self):
        http = FakeHttp(
            post_data={
                "https://ibegin.tcsapps.com/candidate/api/v1/jobs/searchJ": {
                    "data": {
                        "jobs": [
                            {
                                "id": "409127J",
                                "jobTitle": "Analyst",
                                "location": "Chennai",
                                "functionName": "BUSINESS PROCESS SERVICES",
                                "experience": "2-10",
                                "skills": "Commercial Lending",
                            }
                        ]
                    }
                }
            }
        )

        jobs = list(adapter_for("tcs_ibegin", http).list_jobs(Board("TCS", "tcs_ibegin", "analyst")))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_id, "409127J")
        self.assertIn("2-10", jobs[0].description)

    def test_paginated_html_adapter_maps_deloitte(self):
        token = "https://apply.deloitte.com/en_US/careers/SearchJobs/India/?jobRecordsPerPage=10&jobOffset={offset}"
        url = token.replace("{offset}", "0")
        http = FakeHttp(
            text={
                url: """
                    <h3><a href="/en_US/careers/JobDetail/Data-Analytics-Analyst/123">Data Analytics Analyst</a></h3>
                    <p>Deloitte India | Multiple Locations</p>
                """,
                url.replace("jobOffset=0", "jobOffset=10"): "",
            }
        )

        jobs = list(adapter_for("paginated_html", http).list_jobs(Board("Deloitte", "paginated_html", token)))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].location, "India")


if __name__ == "__main__":
    unittest.main()
