from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import dedupe_boards, load_discovered_boards, write_discovered_boards
from .discovery import discover_urls
from .http import HttpClient
from .models import Board, Category
from .sources.ats import adapter_for, board_from_url
from .text import is_india_job, role_score


@dataclass(frozen=True)
class DiscoverySettings:
    enabled_by_default: bool
    max_queries: int
    results_per_query: int
    max_generated_candidates: int
    min_total_jobs: int
    min_india_jobs: int
    target_companies: list[str]
    target_queries: list[str]


@dataclass
class DiscoveryResult:
    added: list[Board]
    candidates_seen: int
    verified: int
    rejected: int
    report_path: Path


def load_discovery_settings(config_dir: Path) -> DiscoverySettings:
    path = config_dir / "discovery.json"
    if not path.exists():
        return DiscoverySettings(
            enabled_by_default=False,
            max_queries=0,
            results_per_query=5,
            max_generated_candidates=0,
            min_total_jobs=1,
            min_india_jobs=1,
            target_companies=[],
            target_queries=[],
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return DiscoverySettings(
        enabled_by_default=bool(data.get("enabled_by_default", False)),
        max_queries=int(data.get("max_queries", 12)),
        results_per_query=int(data.get("results_per_query", 5)),
        max_generated_candidates=int(data.get("max_generated_candidates", 80)),
        min_total_jobs=int(data.get("min_total_jobs", 1)),
        min_india_jobs=int(data.get("min_india_jobs", 1)),
        target_companies=list(data.get("target_companies", [])),
        target_queries=list(data.get("target_queries", [])),
    )


def discover_and_update_boards(
    config_dir: Path,
    output_dir: Path,
    http: HttpClient,
    categories: list[Category],
    existing_boards: list[Board],
) -> DiscoveryResult:
    settings = load_discovery_settings(config_dir)
    queries = _build_board_queries(settings)[: settings.max_queries]
    if not queries:
        return DiscoveryResult([], 0, 0, 0, _write_report(output_dir, []))

    urls = discover_urls(http, queries, limit_per_query=settings.results_per_query)
    existing_keys = {(board.source.lower(), board.token.lower()) for board in existing_boards}
    discovered_existing = load_discovered_boards(config_dir)
    discovered_keys = {(board.source.lower(), board.token.lower()) for board in discovered_existing}

    candidates = []
    for url in urls:
        board = board_from_url(url)
        if not board:
            continue
        key = (board.source.lower(), board.token.lower())
        if key in existing_keys or key in discovered_keys:
            continue
        candidates.append(board)
    candidates.extend(_generated_candidates(settings))
    candidates = [
        board
        for board in dedupe_boards(candidates)
        if (board.source.lower(), board.token.lower()) not in existing_keys
        and (board.source.lower(), board.token.lower()) not in discovered_keys
    ][: settings.max_generated_candidates]

    report_rows = []
    added: list[Board] = []
    for board in candidates:
        row = _verify_board(http, board, categories, settings)
        report_rows.append(row)
        if row["status"] == "accepted":
            added.append(
                Board(
                    company=_company_name(board.token),
                    source=board.source,
                    token=board.token,
                    priority_categories=row["priority_categories"].split("; ") if row["priority_categories"] else [],
                )
            )

    if added:
        write_discovered_boards(config_dir, discovered_existing + added)
    report_path = _write_report(output_dir, report_rows)
    return DiscoveryResult(
        added=added,
        candidates_seen=len(candidates),
        verified=len(report_rows),
        rejected=len([row for row in report_rows if row["status"] != "accepted"]),
        report_path=report_path,
    )


def verify_company_candidates(
    config_dir: Path,
    output_dir: Path,
    candidates_path: Path,
    http: HttpClient,
    categories: list[Category],
    existing_boards: list[Board],
) -> DiscoveryResult:
    if not candidates_path.exists():
        return DiscoveryResult([], 0, 0, 0, _write_company_report(output_dir, []))

    try:
        data = json.loads(candidates_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return DiscoveryResult([], 0, 0, 1, _write_company_report(output_dir, [_company_row("", "invalid_json", error=str(exc))]))

    settings = load_discovery_settings(config_dir)
    discovered_existing = load_discovered_boards(config_dir)
    known_keys = {
        (board.source.lower(), board.token.lower())
        for board in list(existing_boards) + discovered_existing
    }

    report_rows = []
    added: list[Board] = []
    candidates_seen = 0
    for company in data.get("companies", []):
        company_name = str(company.get("company_name", "")).strip()
        urls = [str(url) for url in company.get("career_urls", []) if isinstance(url, str)]
        ats_hint = str(company.get("ats_hint", "unknown")).strip().lower()
        candidate_boards = _boards_from_company_candidate(company_name, urls, ats_hint)
        if not candidate_boards:
            report_rows.append(_company_row(company_name, "no_supported_ats_candidate", urls=urls, ats_hint=ats_hint))
            continue

        for board in candidate_boards:
            candidates_seen += 1
            key = (board.source.lower(), board.token.lower())
            if key in known_keys:
                report_rows.append(_company_row(company_name, "already_known", board=board, urls=urls, ats_hint=ats_hint))
                continue
            row = _verify_board(http, board, categories, settings)
            report_rows.append(_company_row(company_name, row["status"], board=board, urls=urls, ats_hint=ats_hint, verifier_row=row))
            if row["status"] == "accepted":
                known_keys.add(key)
                promoted = Board(
                    company=company_name or _company_name(board.token),
                    source=board.source,
                    token=board.token,
                    priority_categories=row["priority_categories"].split("; ") if row["priority_categories"] else [],
                )
                added.append(promoted)

    if added:
        write_discovered_boards(config_dir, discovered_existing + added)
    report_path = _write_company_report(output_dir, report_rows)
    return DiscoveryResult(
        added=added,
        candidates_seen=candidates_seen,
        verified=len(report_rows),
        rejected=len([row for row in report_rows if row["status"] != "accepted"]),
        report_path=report_path,
    )


def _build_board_queries(settings: DiscoverySettings) -> list[str]:
    queries = []
    ats_sites = [
        "jobs.lever.co",
        "jobs.ashbyhq.com",
        "boards.greenhouse.io",
        "job-boards.eu.greenhouse.io",
        "careers.ey.com",
        "careers.ltimindtree.com",
    ]
    for query in settings.target_queries:
        for site in ats_sites:
            queries.append(f"site:{site} \"{query}\"")
    for company in settings.target_companies:
        for site in ats_sites:
            queries.append(f'site:{site} "{company}" India analyst jobs')
    return queries


def _generated_candidates(settings: DiscoverySettings) -> list[Board]:
    candidates = []
    for company in settings.target_companies:
        for token in _token_variants(company):
            for source in ("lever", "greenhouse", "ashby", "smartrecruiters"):
                candidates.append(Board(company=company, source=source, token=token))
    return candidates


def _boards_from_company_candidate(company_name: str, urls: list[str], ats_hint: str) -> list[Board]:
    boards = []
    for url in urls:
        board = board_from_url(url)
        if board:
            boards.append(Board(company=company_name or _company_name(board.token), source=board.source, token=board.token))

    supported_sources = ("lever", "greenhouse", "ashby", "smartrecruiters")
    sources = [ats_hint] if ats_hint in supported_sources else list(supported_sources)
    for token in _token_variants(company_name):
        for source in sources:
            boards.append(Board(company=company_name, source=source, token=token))
    return dedupe_boards(boards)


def _token_variants(company: str) -> list[str]:
    import re

    words = re.findall(r"[a-z0-9]+", company.lower())
    if not words:
        return []
    compact = "".join(words)
    hyphen = "-".join(words)
    variants = [compact]
    if hyphen != compact:
        variants.append(hyphen)
    if len(words) > 1:
        variants.append(words[0])
    return list(dict.fromkeys(variants))


def _verify_board(http: HttpClient, board: Board, categories: list[Category], settings: DiscoverySettings) -> dict[str, str]:
    fast_http = HttpClient(timeout=8, retries=0, pause_seconds=0.1)
    try:
        jobs = list(adapter_for(board.source, fast_http).list_jobs(board))
    except Exception as exc:
        return _row(board, "failed", error=str(exc))

    india_jobs = [job for job in jobs if is_india_job(job.location, job.description)]
    category_hits: dict[str, int] = {}
    for category in categories:
        hits = 0
        for job in india_jobs:
            score, _matches = role_score(job.title, job.description, category.target_roles, category.positive_keywords)
            if score >= 45:
                hits += 1
        if hits:
            category_hits[category.id] = hits

    if len(jobs) < settings.min_total_jobs:
        status = "rejected_no_jobs"
    elif len(india_jobs) < settings.min_india_jobs:
        status = "rejected_no_india_jobs"
    elif not category_hits:
        status = "rejected_no_category_match"
    else:
        status = "accepted"

    return _row(
        board,
        status,
        jobs_found=len(jobs),
        india_jobs=len(india_jobs),
        priority_categories="; ".join(sorted(category_hits, key=category_hits.get, reverse=True)),
    )


def _row(
    board: Board,
    status: str,
    jobs_found: int = 0,
    india_jobs: int = 0,
    priority_categories: str = "",
    error: str = "",
) -> dict[str, str]:
    return {
        "source": board.source,
        "token": board.token,
        "company": _company_name(board.token),
        "status": status,
        "jobs_found": str(jobs_found),
        "india_jobs": str(india_jobs),
        "priority_categories": priority_categories,
        "error": error,
    }


def _write_report(output_dir: Path, rows: list[dict[str, str]]) -> Path:
    import csv

    path = output_dir / "health" / "board_discovery_latest.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["source", "token", "company", "status", "jobs_found", "india_jobs", "priority_categories", "error"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _company_row(
    company_name: str,
    status: str,
    board: Board | None = None,
    urls: list[str] | None = None,
    ats_hint: str = "",
    verifier_row: dict[str, str] | None = None,
    error: str = "",
) -> dict[str, str]:
    verifier_row = verifier_row or {}
    return {
        "company_name": company_name,
        "status": status,
        "source": board.source if board else verifier_row.get("source", ""),
        "token": board.token if board else verifier_row.get("token", ""),
        "ats_hint": ats_hint,
        "jobs_found": verifier_row.get("jobs_found", ""),
        "india_jobs": verifier_row.get("india_jobs", ""),
        "priority_categories": verifier_row.get("priority_categories", ""),
        "career_urls": "; ".join(urls or []),
        "error": error or verifier_row.get("error", ""),
    }


def _write_company_report(output_dir: Path, rows: list[dict[str, str]]) -> Path:
    import csv

    path = output_dir / "health" / "company_candidate_verification_latest.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "company_name",
        "status",
        "source",
        "token",
        "ats_hint",
        "jobs_found",
        "india_jobs",
        "priority_categories",
        "career_urls",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _company_name(token: str) -> str:
    return token.replace("-", " ").replace("_", " ").replace(".", " ").title()
