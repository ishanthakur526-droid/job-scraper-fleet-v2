from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import BoardHealth, Category, JobResult


HEALTH_COLUMNS = ["Company", "Source", "Token", "Status", "Jobs Found", "Error", "Retrieved At"]


def run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_health_report(output_dir: Path, run_id_value: str, health: list[BoardHealth]) -> tuple[Path, Path]:
    health_dir = output_dir / "health"
    health_dir.mkdir(parents=True, exist_ok=True)
    dated_path = health_dir / f"source_health_{run_id_value}.csv"
    latest_path = health_dir / "source_health_latest.csv"
    for path in (dated_path, latest_path):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEALTH_COLUMNS)
            writer.writeheader()
            for item in health:
                writer.writerow(
                    {
                        "Company": item.company,
                        "Source": item.source,
                        "Token": item.token,
                        "Status": item.status,
                        "Jobs Found": item.jobs_found,
                        "Error": item.error,
                        "Retrieved At": item.retrieved_at,
                    }
                )
    return dated_path, latest_path


def write_run_report(
    output_dir: Path,
    run_id_value: str,
    categories: list[Category],
    buckets: dict[str, list[JobResult]],
    new_buckets: dict[str, list[JobResult]],
    health: list[BoardHealth],
    started_at: str,
    finished_at: str,
    possible_buckets: dict[str, list[JobResult]] | None = None,
) -> tuple[Path, Path]:
    reports_dir = output_dir / "reports"
    logs_dir = output_dir / "logs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    failed = [item for item in health if item.status == "failed"]
    empty = [item for item in health if item.status == "empty"]
    summary = {
        "run_id": run_id_value,
        "started_at": started_at,
        "finished_at": finished_at,
        "boards_total": len(health),
        "boards_failed": len(failed),
        "boards_empty": len(empty),
        "expired_or_missing": _missing_count(output_dir),
        "categories": {
            category.id: {
                "current_matches": len(buckets.get(category.id, [])),
                "new_matches": len(new_buckets.get(category.id, [])),
                "possible_matches": len((possible_buckets or {}).get(category.id, [])),
                "high_confidence": len([item for item in buckets.get(category.id, []) if item.quality_tier == "high_confidence"]),
                "needs_review": len([item for item in buckets.get(category.id, []) if item.quality_tier == "needs_review"]),
            }
            for category in categories
        },
    }

    json_path = logs_dir / f"run_{run_id_value}.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    summary_path = reports_dir / "daily_summary_latest.md"
    lines = [
        f"# Job Scraper Daily Summary",
        "",
        f"- Run ID: `{run_id_value}`",
        f"- Started: `{started_at}`",
        f"- Finished: `{finished_at}`",
        f"- Boards checked: `{len(health)}`",
        f"- Board failures: `{len(failed)}`",
        f"- Empty boards: `{len(empty)}`",
        f"- Previously seen jobs missing today: `{summary['expired_or_missing']}`",
        "",
        "| Category | Current Matches | New Today | Possible Matches | High Confidence | Needs Review |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category in categories:
        item = summary["categories"][category.id]
        lines.append(
            f"| {category.name} | {item['current_matches']} | {item['new_matches']} | {item['possible_matches']} | {item['high_confidence']} | {item['needs_review']} |"
        )
    if failed:
        lines.extend(["", "## Failed Sources"])
        lines.extend(f"- {item.company} ({item.source}:{item.token}) - {item.error}" for item in failed[:20])
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, summary_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _missing_count(output_dir: Path) -> int:
    path = output_dir / "state" / "expired_or_missing_jobs.csv"
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        return max(sum(1 for _line in handle) - 1, 0)
