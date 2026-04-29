from __future__ import annotations

import argparse
from pathlib import Path

from .board_discovery import discover_and_update_boards, load_discovery_settings, verify_company_candidates
from .config import load_boards, load_categories
from .discovery import build_queries, discover_urls
from .exporters import export_category, export_new_only, export_possible_matches, export_quality_tiers, export_rejected_jobs
from .history import mark_new_jobs
from .http import HttpClient
from .pipeline import JobPipeline
from .reports import run_id, utc_now, write_health_report, write_run_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Job Scraper Fleet v2 pipeline.")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--category", choices=["all", "data_bi", "research", "excel_mis"], default="all")
    parser.add_argument("--max-per-category", type=int, default=40)
    parser.add_argument("--include-search", action="store_true")
    parser.add_argument("--discover-boards", action="store_true")
    parser.add_argument("--skip-discover-boards", action="store_true")
    parser.add_argument("--company-candidates", type=Path)
    parser.add_argument("--state-dir", type=Path)
    args = parser.parse_args()
    run_id_value = run_id()
    started_at = utc_now()
    state_dir = args.state_dir or (args.output_dir / "state")

    categories = load_categories(args.config_dir)
    if args.category != "all":
        categories = [category for category in categories if category.id == args.category]

    http = HttpClient()
    pipeline = JobPipeline(http)
    boards, seed_urls = load_boards(args.config_dir)
    if args.company_candidates and args.company_candidates.exists():
        print(f"Verifying company scout candidates from {args.company_candidates}...")
        company_discovery = verify_company_candidates(
            args.config_dir,
            args.output_dir,
            args.company_candidates,
            http,
            categories,
            boards,
        )
        print(
            f"Company candidate verification: {len(company_discovery.added)} added, "
            f"{company_discovery.verified} rows checked, {company_discovery.rejected} rejected/skipped. "
            f"Report: {company_discovery.report_path}"
        )
        if company_discovery.added:
            boards, seed_urls = load_boards(args.config_dir)

    discovery_settings = load_discovery_settings(args.config_dir)
    should_discover = args.discover_boards or (discovery_settings.enabled_by_default and not args.skip_discover_boards)
    if should_discover:
        print("Discovering and validating new ATS boards...")
        discovery = discover_and_update_boards(args.config_dir, args.output_dir, http, categories, boards)
        print(
            f"Board discovery: {len(discovery.added)} added, "
            f"{discovery.verified} verified, {discovery.rejected} rejected. "
            f"Report: {discovery.report_path}"
        )
        if discovery.added:
            boards, seed_urls = load_boards(args.config_dir)

    print(f"Collecting from {len(boards)} configured ATS boards...")
    jobs, health = pipeline.collect_from_boards(boards)
    print(f"Collected {len(jobs)} structured jobs from configured boards.")

    discovered_urls = list(seed_urls)
    if args.include_search:
        queries = []
        for category in categories:
            queries.extend(build_queries(category.name, category.target_roles))
        print(f"Discovering ATS URLs from {len(queries)} search queries...")
        discovered_urls.extend(discover_urls(http, queries))
        print(f"Discovered {len(discovered_urls)} candidate URLs.")

    if discovered_urls:
        jobs.extend(pipeline.collect_from_urls(discovered_urls))
        print(f"Total collected jobs after URL expansion: {len(jobs)}")

    buckets = pipeline.classify(jobs, categories, max_per_category=args.max_per_category)
    possible_buckets, rejected_jobs = pipeline.discover_false_negatives(jobs, categories, buckets)
    new_buckets = mark_new_jobs(state_dir, buckets)
    for category in categories:
        results = buckets.get(category.id, [])
        legacy_path, _audit_path = export_category(args.output_dir, category, results)
        new_path = export_new_only(args.output_dir, category, new_buckets.get(category.id, []))
        export_quality_tiers(args.output_dir, category, results)
        possible_path = export_possible_matches(args.output_dir, category, possible_buckets.get(category.id, []))
        print(
            f"{category.name}: wrote {len(results)} current rows to {legacy_path}; "
            f"{len(new_buckets.get(category.id, []))} new rows to {new_path}; "
            f"{len(possible_buckets.get(category.id, []))} possible matches to {possible_path}"
        )
    rejected_path = export_rejected_jobs(args.output_dir, rejected_jobs)
    print(f"Rejected-job audit: {rejected_path}")

    health_path, _latest_health_path = write_health_report(args.output_dir, run_id_value, health)
    finished_at = utc_now()
    log_path, summary_path = write_run_report(
        args.output_dir,
        run_id_value,
        categories,
        buckets,
        new_buckets,
        health,
        started_at,
        finished_at,
        possible_buckets,
    )
    print(f"Health report: {health_path}")
    print(f"Run log: {log_path}")
    print(f"Daily summary: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
