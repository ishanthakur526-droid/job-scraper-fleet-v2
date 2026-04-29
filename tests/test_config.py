import json
import uuid
import unittest
from pathlib import Path

from jobfleet.config import load_boards


class ConfigTests(unittest.TestCase):
    def test_load_boards_includes_generated_discovered_boards(self):
        config_dir = Path.cwd() / "job_scraper_fleet_v2" / ".test_tmp" / str(uuid.uuid4())
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "boards.json").write_text(
            json.dumps(
                {
                    "boards": [
                        {"company": "Manual", "source": "lever", "token": "manual", "priority_categories": []}
                    ],
                    "seed_urls": [],
                }
            ),
            encoding="utf-8",
        )
        (config_dir / "discovered_boards.json").write_text(
            json.dumps(
                {
                    "boards": [
                        {"company": "Generated", "source": "ashby", "token": "generated", "priority_categories": []}
                    ]
                }
            ),
            encoding="utf-8",
        )

        boards, _seed_urls = load_boards(config_dir)

        self.assertEqual([(board.source, board.token) for board in boards], [("lever", "manual"), ("ashby", "generated")])


if __name__ == "__main__":
    unittest.main()
