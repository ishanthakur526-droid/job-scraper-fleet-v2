import unittest

from jobfleet.models import Board
from jobfleet.sources.ats import adapter_for, board_from_url


class FakeHttp:
    def __init__(self, pages):
        self.pages = pages

    def get_text(self, url, accept="text/html,application/json"):
        if url not in self.pages:
            raise AssertionError(f"Unexpected URL: {url}")
        return self.pages[url]


class SuccessFactorsTests(unittest.TestCase):
    def test_adapter_reads_listing_and_detail_pages(self):
        listing_url = "https://careers.example.com/search/?q=analyst&locationsearch=India"
        detail_url = "https://careers.example.com/job/Bengaluru-Data-Analyst-KA/123/"
        http = FakeHttp(
            {
                listing_url: f"""
                    <table>
                      <tr>
                        <td><a href="{detail_url}">Data Analyst</a></td>
                        <td>Bengaluru, KA, IN</td>
                      </tr>
                    </table>
                """,
                f"{listing_url}&startrow=25": "<table></table>",
                detail_url: """
                    <html>
                      <head><title>Data Analyst | Careers</title></head>
                      <body>
                        <h1>Data Analyst</h1>
                        <p>Location: Bengaluru, KA, IN Date: Apr 28, 2026</p>
                        <p>Use SQL, Excel, Power BI and dashboards. 1-3 years experience.</p>
                      </body>
                    </html>
                """,
            }
        )
        board = Board("Example", "successfactors", listing_url, ["data_bi"])

        jobs = list(adapter_for("successfactors", http).list_jobs(board))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "Example")
        self.assertEqual(jobs[0].title, "Data Analyst")
        self.assertEqual(jobs[0].location, "Bengaluru, KA, IN")
        self.assertEqual(jobs[0].source_id, "123")
        self.assertIn("Power BI", jobs[0].description)

    def test_board_from_url_recognizes_known_successfactors_sites(self):
        self.assertEqual(board_from_url("https://careers.ey.com/ey/search/?q=analyst").source, "successfactors")
        self.assertEqual(
            board_from_url("https://careers.ltimindtree.com/search/?q=DATA").source,
            "successfactors",
        )


if __name__ == "__main__":
    unittest.main()
