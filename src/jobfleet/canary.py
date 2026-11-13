"""Link canaries: open 1-2 output links per source each run.

A systematic link bug (like v2's Amazon UUID links) makes every link of a
source fail at once, so a small sample per source is enough to catch it.
"""

from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from .exporters import write_csv
from .http import FetchError, HttpClient
from .models import JobResult

COLUMNS = ["Source", "Status", "Reason", "HTTP", "URL", "Final URL"]
_SOFT_404_RE = re.compile(
    r"page not found|job not found|no longer (?:available|accepting|open|active)|position (?:has been )?(?:filled|closed)"
    r"|this (?:job|position|requisition) (?:is|has been) (?:closed|expired|removed)|job (?:has )?expired|\b404\b",
    re.IGNORECASE,
)


def pick_canaries(results: list[JobResult], per_source: int = 2) -> list[JobResult]:
    by_source: dict[str, list[JobResult]] = defaultdict(list)
    for result in results:
        if result.url and len(by_source[result.source]) < per_source:
            by_source[result.source].append(result)
    return [item for items in by_source.values() for item in items]


def check(http: HttpClient, result: JobResult) -> dict[str, str]:
    row = {"source": result.source, "url": result.url, "status": "pass", "reason": "", "http": "", "final_url": ""}
    try:
        response = http.request("GET", result.url, accept="text/html", raise_for_status=False, retries=1, timeout=20)
    except FetchError as exc:
        row.update(status="warn", reason=f"unreachable: {exc}"[:200])
        return row
    row["http"] = str(response.status)
    row["final_url"] = response.url
    if response.status in (404, 410):
        row.update(status="fail", reason=f"HTTP {response.status}")
        return row
    if response.status >= 400:
        row.update(status="warn", reason=f"HTTP {response.status} (blocked or rate limited)")
        return row
    head = " ".join(re.findall(r"<(?:title|h1)[^>]*>(.*?)</(?:title|h1)>", response.text[:200_000], flags=re.I | re.S))
    if _SOFT_404_RE.search(re.sub(r"<[^>]+>", " ", head)):
        row.update(status="fail", reason="page says the job is not found/closed")
        return row
    original, final = urlparse(result.url), urlparse(response.url)
    if final.path.rstrip("/") in ("", "/search", "/jobs", "/careers") and original.path.rstrip("/") != final.path.rstrip("/"):
        row.update(status="fail", reason="redirected to a generic listing page")
    return row


def run_canaries(http: HttpClient, results: list[JobResult], output_dir: Path, per_source: int = 2) -> list[dict[str, str]]:
    sample = pick_canaries(results, per_source)
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="canary") as pool:
        rows = list(pool.map(lambda r: check(http, r), sample))
    write_csv(
        output_dir / "health" / "canary_links_latest.csv",
        COLUMNS,
        (
            {"Source": r["source"], "Status": r["status"], "Reason": r["reason"], "HTTP": r["http"], "URL": r["url"], "Final URL": r["final_url"]}
            for r in rows
        ),
    )
    return rows
