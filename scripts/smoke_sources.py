"""Live smoke test: one board per source, small time budget, plus a link check.

    python scripts/smoke_sources.py            # every source in config/companies.json
    python scripts/smoke_sources.py workday    # only the named sources

Hits real websites; not part of the unit tests or CI.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jobfleet.canary import check  # noqa: E402
from jobfleet.classifier import Classifier  # noqa: E402
from jobfleet.config import load_boards  # noqa: E402
from jobfleet.http import FetchError, HttpClient  # noqa: E402
from jobfleet.pipeline import to_result  # noqa: E402
from jobfleet.profile import load_profile  # noqa: E402
from jobfleet.sources import AdapterContext, adapter_for  # noqa: E402


def main(only: list[str]) -> int:
    classifier = Classifier.from_profile(load_profile(ROOT / "profile.toml"))
    boards, _ = load_boards(ROOT / "config", include_disabled=False)
    picked = {}
    for board in boards:
        if (not only or board.source in only) and board.source not in picked:
            picked[board.source] = board
    http = HttpClient()
    failures = 0
    for source, board in picked.items():
        started = time.monotonic()
        try:
            adapter = adapter_for(source, http, AdapterContext(prefilter=classifier.prefilter, budget_s=30))
            jobs = adapter.list_jobs(board)
        except (FetchError, ValueError) as exc:
            failures += 1
            print(f"FAIL {source:16} {board.company[:24]:24} {exc}")
            continue
        link = "-"
        if jobs:
            ev = classifier.evaluate(jobs[0])
            link = check(http, to_result(ev))["status"]
        print(f"OK   {source:16} {board.company[:24]:24} {len(jobs):5} jobs in {time.monotonic() - started:5.1f}s  link={link}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
