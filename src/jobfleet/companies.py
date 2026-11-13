"""my_companies.txt (paste careers links, one per line) and `jobfleet add-company`."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .models import Board
from .sources import board_from_url

HEADER = """\
# Your own companies: paste careers-page links, one per line, then run JobFleet again.
# Works best with job-board links (Workday, Greenhouse, Lever, Ashby, SmartRecruiters, Oracle):
#   https://boards.greenhouse.io/airbnb
#   https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
# Optional name in front:   Airbnb | https://boards.greenhouse.io/airbnb
# Not sure which link is the job board? Run:  jobfleet add-company https://company.com/careers
"""


def default_path(config_dir: Path) -> Path:
    return config_dir.resolve().parent / "my_companies.txt"


def parse_line(line: str) -> Board | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    text = re.split(r"\s+#\s", text, maxsplit=1)[0].strip()  # "url  # note"; '#' inside a URL is kept
    name, _, url = text.rpartition("|") if "|" in text else ("", "", text)
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return None
    board = board_from_url(url) or Board(company=urlparse(url).netloc, source="generic_html", token=url)
    if name.strip():
        board = Board(company=name.strip(), source=board.source, token=board.token, options=board.options)
    return board


def load_my_companies(path: Path) -> list[Board]:
    if not path.exists():
        return []
    boards = [parse_line(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]
    return [board for board in boards if board]


def append(path: Path, name: str, url: str) -> None:
    if not path.exists():
        path.write_text(HEADER, encoding="utf-8")
    existing = path.read_text(encoding="utf-8")
    if url in existing:
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(("" if existing.endswith("\n") else "\n") + (f"{name} | {url}" if name else url) + "\n")


def add_company(url: str, name: str, path: Path, http, classifier=None) -> int:
    """Find the job board behind a careers page, check it, and save it to my_companies.txt."""
    from .discovery import _extract_ats_urls
    from .http import FetchError

    board = board_from_url(url)
    resolved = url
    if board is None:
        print(f"Looking for a job board on {url} ...")
        try:
            html = http.get_text(url)
        except FetchError as exc:
            print(f"Could not open that page ({exc}).")
            return 1
        for candidate in _extract_ats_urls(html):
            board = board_from_url(candidate)
            if board:
                resolved = candidate
                break
    if board is None:
        print("No supported job board found on that page; it is saved anyway and JobFleet will read job postings")
        print("published on it (schema.org JobPosting). For best results, find the company's Workday/Greenhouse/Lever link.")
        append(path, name, url)
        return 0
    label = name or board.company
    print(f"Found: {board.source} board '{board.token}'")
    if classifier is not None:
        from .board_discovery import verify_board

        result = verify_board(http, Board(company=label, source=board.source, token=board.token, options=board.options), classifier)
        if result["status"] == "failed":
            print(f"It could not be read right now: {result['error']}")
        else:
            print(f"{result['jobs_found']} open jobs, {result['india_jobs']} in your countries, {result['accepted_jobs']} matching your profile today.")
    append(path, label, resolved)
    print(f"Saved to {path.name}. It is checked on every run from now on.")
    return 0
