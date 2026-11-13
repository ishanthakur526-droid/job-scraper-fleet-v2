"""Deterministic verification of candidate career boards.

Candidates come from the weekly Claude company scout (or an optional manual
web-search pass). A board is promoted to ``config/discovered_boards.json`` only
if it returns live jobs, some in India, and at least one that the production
classifier accepts. Rejections are cached for 30 days so the same dead
candidates are not re-probed every run (v2 re-probed ~100 failures daily).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .classifier import Classifier
from .config import dedupe_boards, load_discovered_boards, write_discovered_boards
from .discovery import discover_urls
from .exporters import write_csv
from .geo import resolve
from .http import FetchError, HttpClient
from .models import Board
from .sources import AdapterContext, adapter_for, board_from_url

log = logging.getLogger(__name__)

NEGATIVE_CACHE_DAYS = 30
VERIFY_COLUMNS = ["company_name", "status", "source", "token", "jobs_found", "india_jobs", "accepted_jobs", "priority_categories", "career_urls", "error"]


@dataclass
class DiscoveryResult:
    added: list[Board]
    verified: int
    rejected: int
    report_path: Path | None


def verify_board(http: HttpClient, board: Board, classifier: Classifier, budget_s: float = 90.0) -> dict[str, Any]:
    context = AdapterContext(prefilter=classifier.prefilter, budget_s=budget_s)
    try:
        jobs = adapter_for(board.source, http, context).list_jobs(board)
    except (FetchError, ValueError) as exc:
        return {"status": "failed", "error": str(exc)[:300], "jobs_found": 0, "india_jobs": 0, "accepted_jobs": 0, "priority_categories": ""}
    except Exception as exc:  # unexpected payloads must not break the run
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300], "jobs_found": 0, "india_jobs": 0, "accepted_jobs": 0, "priority_categories": ""}
    india = [job for job in jobs if resolve(job.location, job.country_codes, job.locations, job.description).is_india]
    hits: Counter[str] = Counter()
    for job in india:
        evaluation = classifier.evaluate(job)
        if evaluation.decision == "accept":
            hits[evaluation.category_id] += 1
    if not jobs:
        status = "rejected_no_jobs"
    elif not india:
        status = "rejected_no_india_jobs"
    elif not hits:
        status = "rejected_no_category_match"
    else:
        status = "accepted"
    return {
        "status": status,
        "error": "",
        "jobs_found": len(jobs),
        "india_jobs": len(india),
        "accepted_jobs": sum(hits.values()),
        "priority_categories": "; ".join(category for category, _n in hits.most_common()),
    }


def verify_company_candidates(
    config_dir: Path,
    output_dir: Path,
    candidates: dict[str, Any],
    http: HttpClient,
    classifier: Classifier,
    existing_boards: list[Board],
    state: Any = None,
) -> DiscoveryResult:
    known = {board.key for board in existing_boards} | {board.key for board in load_discovered_boards(config_dir)}
    rows: list[dict[str, Any]] = []
    added: list[Board] = []
    for company in candidates.get("companies", []) if isinstance(candidates, dict) else []:
        name = str(company.get("company_name", "")).strip()
        urls = [str(url) for url in company.get("career_urls", []) if isinstance(url, str)]
        boards = dedupe_boards([b for b in (board_from_url(url) for url in urls) if b])
        if not boards:
            rows.append(_row(name, "no_supported_ats_url", urls=urls))
            continue
        for candidate in boards:
            board = Board(company=name or candidate.company, source=candidate.source, token=candidate.token, options=candidate.options)
            if board.key in known:
                rows.append(_row(name, "already_known", board, urls))
                continue
            cached = state.cache_get("probe_cache", board.key, NEGATIVE_CACHE_DAYS) if state else None
            if cached and cached.get("status") != "accepted":
                rows.append(_row(name, f"cached_{cached.get('status')}", board, urls))
                continue
            result = verify_board(http, board, classifier)
            if state:
                state.probe_put(board.key, result["status"], result.get("error", ""))
            rows.append(_row(name, result["status"], board, urls, result))
            if result["status"] == "accepted":
                known.add(board.key)
                added.append(
                    Board(
                        company=board.company,
                        source=board.source,
                        token=board.token,
                        priority_categories=[c for c in result["priority_categories"].split("; ") if c],
                        options=board.options,
                        note=f"added by company scout {date.today().isoformat()}",
                    )
                )
    if added:
        write_discovered_boards(config_dir, load_discovered_boards(config_dir) + added)
    report = write_csv(output_dir / "health" / "company_candidate_verification_latest.csv", VERIFY_COLUMNS, rows)
    return DiscoveryResult(added=added, verified=len(rows), rejected=sum(r["status"] != "accepted" for r in rows), report_path=report)


def discover_boards_by_search(
    config_dir: Path,
    output_dir: Path,
    http: HttpClient,
    classifier: Classifier,
    existing_boards: list[Board],
    queries: list[str],
    state: Any = None,
) -> DiscoveryResult:
    """Optional manual pass (``--discover-boards``): free web search for ATS URLs, then verify."""
    urls = discover_urls(http, queries, limit_per_query=6)
    payload = {"companies": [{"company_name": "", "career_urls": [url]} for url in urls]}
    return verify_company_candidates(config_dir, output_dir, payload, http, classifier, existing_boards, state)


def _row(name: str, status: str, board: Board | None = None, urls: list[str] | None = None, result: dict | None = None) -> dict[str, Any]:
    result = result or {}
    return {
        "company_name": name,
        "status": status,
        "source": board.source if board else "",
        "token": board.token if board else "",
        "jobs_found": result.get("jobs_found", ""),
        "india_jobs": result.get("india_jobs", ""),
        "accepted_jobs": result.get("accepted_jobs", ""),
        "priority_categories": result.get("priority_categories", ""),
        "career_urls": "; ".join(urls or []),
        "error": result.get("error", ""),
    }


def load_candidates_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read company candidates %s: %s", path, exc)
        return {}
