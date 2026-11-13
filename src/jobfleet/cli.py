from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

from . import __version__
from .board_discovery import discover_boards_by_search, load_candidates_file, verify_company_candidates
from .canary import run_canaries
from .classifier import Classifier
from .config import load_boards, load_llm_config, load_taxonomy
from .discovery import build_queries, discover_urls
from .exporters import export_category, export_new_only, export_overflow, export_quality_tiers, export_rejected_jobs, export_review_file
from .http import HttpClient, OfflineHttpClient
from .llm import ClaudeRunner, clear_backoff
from .pipeline import JobPipeline
from .rawdump import prune_dumps, read_dump, write_dump
from .reports import run_id, utc_now, write_health_report, write_run_report
from .scout import run_scout
from .state import StateStore
from .triage import run_triage

log = logging.getLogger("jobfleet")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Job Scraper Fleet v3: India early-career analyst jobs from public career APIs.")
    parser.add_argument("--version", action="version", version=f"jobfleet {__version__}")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--state-dir", type=Path, help="defaults to <output-dir>/state")
    parser.add_argument("--category", choices=["all", "data_bi", "research", "excel_mis"], default="all")
    parser.add_argument("--max-per-category", type=int, default=40)
    parser.add_argument("--per-company-cap", type=int, default=8, help="max rows per company in each main list (rest -> overflow)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--board-budget", type=float, default=120.0, help="seconds per board before it is marked partial")
    parser.add_argument("--include-linkedin", action="store_true", help="opt in to LinkedIn public job search (against LinkedIn ToS)")
    parser.add_argument("--include-search", action="store_true", help="also expand seed URLs found by free web search")
    parser.add_argument("--discover-boards", action="store_true", help="manual: search the web for new ATS boards and verify them")
    parser.add_argument("--skip-discover-boards", action="store_true", help=argparse.SUPPRESS)  # v2 compatibility (now default)
    parser.add_argument("--company-candidates", type=Path, help="verify a company-candidates JSON file now")
    parser.add_argument("--skip-llm", action="store_true", help="no Claude calls this run")
    parser.add_argument("--skip-scout", action="store_true")
    parser.add_argument("--skip-triage", action="store_true")
    parser.add_argument("--force-scout", action="store_true", help="run the weekly Claude company scout now")
    parser.add_argument("--replay", type=Path, help="reclassify a raw dump offline (no network, no scout)")
    parser.add_argument("--no-dump-raw", action="store_true")
    parser.add_argument("--no-canaries", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser


def setup_logging(output_dir: Path, run_id_value: str, level: str) -> Path:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{run_id_value}.log"
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(file_handler)
    return log_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id_value = run_id()
    log_path = setup_logging(args.output_dir, run_id_value, args.log_level)
    try:
        return run(args, run_id_value)
    except Exception:
        log.exception("Run failed; see %s", log_path)
        return 1


def run(args: argparse.Namespace, run_id_value: str) -> int:
    started = time.monotonic()
    started_at = utc_now()
    output_dir: Path = args.output_dir
    state_dir: Path = args.state_dir or (output_dir / "state")
    categories, adjacent = load_taxonomy(args.config_dir)
    if args.category != "all":
        categories = [c for c in categories if c.id == args.category]
    classifier = Classifier(categories, adjacent)
    llm_config = load_llm_config(args.config_dir)
    use_llm = bool(llm_config.get("enabled", True)) and not args.skip_llm and not args.replay
    state = StateStore(state_dir / "jobfleet.sqlite")
    if args.force_scout:
        clear_backoff(state)  # e.g. right after `claude auth login`: retry Claude now
    imported = state.import_legacy_history(state_dir / "job_history.csv")
    if imported:
        log.info("Migrated %s rows of v2 history into %s", imported, state.path.name)

    http = OfflineHttpClient() if args.replay else HttpClient()
    pipeline = JobPipeline(
        http,
        classifier,
        workers=args.workers,
        board_budget_s=args.board_budget,
        max_per_category=args.max_per_category,
        per_company_cap=args.per_company_cap,
    )
    boards, seed_urls = load_boards(args.config_dir)
    if not args.include_linkedin:
        boards = [b for b in boards if b.source != "linkedin_guest"]
    runner = ClaudeRunner(
        output_dir / "llm_sandbox",
        configured_exe=str(llm_config.get("claude_exe") or ""),
        model=str(llm_config.get("model", "sonnet")),
        effort=str(llm_config.get("effort", "low")),
        isolate_settings=bool(llm_config.get("isolate_settings", True)),
    )

    if args.replay:
        meta, jobs, health = read_dump(args.replay)
        log.info("Replaying %s raw jobs from %s (run %s)", len(jobs), args.replay, meta.get("run_id"))
    else:
        if args.company_candidates:
            result = verify_company_candidates(args.config_dir, output_dir, load_candidates_file(args.company_candidates), http, classifier, boards, state)
            log.info("Candidate verification: %s added, %s checked (%s)", len(result.added), result.verified, result.report_path)
        if args.discover_boards:
            queries = [f'site:{site} "{q}"' for q in ("Data Analyst India", "MIS Analyst India", "Research Analyst India") for site in ("jobs.lever.co", "boards.greenhouse.io", "jobs.ashbyhq.com", "myworkdayjobs.com")]
            result = discover_boards_by_search(args.config_dir, output_dir, http, classifier, boards, queries, state)
            log.info("Board discovery: %s added, %s checked", len(result.added), result.verified)
        if args.company_candidates or args.discover_boards:
            boards, seed_urls = load_boards(args.config_dir)
            if not args.include_linkedin:
                boards = [b for b in boards if b.source != "linkedin_guest"]
        quarantined = state.quarantined()
        log.info("Collecting from %s boards (%s quarantined) with %s workers...", len(boards), len(quarantined), args.workers)
        jobs, health = pipeline.collect_from_boards(boards, quarantined)
        urls = list(seed_urls)
        if args.include_search:
            queries = [q for c in categories for q in build_queries(c.name, [r if isinstance(r, str) else r.get("title", "") for r in c.target_roles])]
            urls.extend(discover_urls(http, queries))
        if urls:
            extra_jobs, extra_health = pipeline.collect_from_urls(urls)
            jobs.extend(extra_jobs)
            health.extend(extra_health)
        for item in health:
            state.update_board(item)
        if not args.no_dump_raw:
            write_dump(output_dir / "raw" / f"{run_id_value}.jsonl.gz", run_id_value, jobs, health)
            prune_dumps(output_dir / "raw")
    log.info("Collected %s raw jobs; classifying...", len(jobs))

    evaluations = pipeline.evaluate(jobs)
    buckets = pipeline.build(evaluations)
    llm_stats: dict[str, str] = {}
    if use_llm and not args.skip_triage:
        llm_stats["Triage"] = run_triage(runner, buckets, state, llm_config, output_dir)
        log.info("Claude triage: %s", llm_stats["Triage"])

    state.record_results(buckets.recorded())
    succeeded = {h.board_key for h in health if h.status in ("ok", "empty")}
    by_source: dict[str, set[str]] = defaultdict(set)
    for item in health:
        by_source[item.source].add(item.status)
    sources_ok = {source for source, statuses in by_source.items() if statuses <= {"ok", "empty"}}
    newly_missing = state.mark_presence(jobs, succeeded, sources_ok)
    state.prune()

    new_rows: dict[str, list] = {}
    for category in categories:
        current = buckets.main.get(category.id, [])
        overflow = buckets.overflow.get(category.id, [])
        new_rows[category.id] = [row for row in current + overflow if row.is_new]
        export_category(output_dir, category, current)
        export_new_only(output_dir, category, new_rows[category.id])
        export_quality_tiers(output_dir, category, current, buckets.possible.get(category.id, []))
        export_overflow(output_dir, category, overflow)
        log.info(
            "%-12s %3d current (%d new), %d overflow, %d possible",
            category.name, len(current), len(new_rows[category.id]), len(overflow), len(buckets.possible.get(category.id, [])),
        )
    if adjacent:
        export_review_file(output_dir / adjacent.output, buckets.adjacent)
    export_review_file(output_dir / "aggregator_review_today.csv", buckets.aggregator)
    export_rejected_jobs(output_dir, buckets.rejected)
    canaries = [] if (args.replay or args.no_canaries) else run_canaries(http, [r for rows in buckets.main.values() for r in rows] + buckets.adjacent, output_dir)
    for row in canaries:
        if row["status"] == "fail":
            log.warning("Link canary failed for %s: %s (%s)", row["source"], row["reason"], row["url"])

    if use_llm and not args.skip_scout:
        broken = sorted({h.company for h in health if h.status == "quarantined" or (h.status == "failed" and h.hard_failure)})
        llm_stats["Company scout"] = run_scout(runner, args.config_dir, output_dir, state, http, classifier, boards, llm_config, broken, force=args.force_scout)
        log.info("Company scout: %s", llm_stats["Company scout"])
    elif not use_llm:
        llm_stats["Claude"] = "skipped (--skip-llm, replay, or disabled in config)"

    write_health_report(output_dir, run_id_value, health)
    stats = {
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_s": round(time.monotonic() - started, 1),
        "raw_jobs": len(jobs),
        "newly_missing": newly_missing,
        "http_requests": sum(http.stats.values()),
        "_canaries": canaries,
        "_llm": llm_stats,
    }
    json_path, summary_path = write_run_report(output_dir, run_id_value, categories, buckets, new_rows, health, stats)
    state.export_csv_views(state_dir)
    state.close()
    log.info("Done in %.0fs. Summary: %s", time.monotonic() - started, summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
