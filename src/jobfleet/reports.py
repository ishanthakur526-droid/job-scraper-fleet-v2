from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .exporters import write_csv
from .models import BoardHealth, Category, JobResult

HEALTH_COLUMNS = ["Company", "Source", "Token", "Status", "Jobs Found", "Duration (s)", "Hard Failure", "Note", "Error", "Retrieved At"]
NEWLY_POSTED_DAYS = 7


def run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_health_report(output_dir: Path, run_id_value: str, health: list[BoardHealth]) -> Path | None:
    rows = [
        {
            "Company": item.company,
            "Source": item.source,
            "Token": item.token,
            "Status": item.status,
            "Jobs Found": item.jobs_found,
            "Duration (s)": item.duration_s,
            "Hard Failure": "yes" if item.hard_failure else "",
            "Note": item.note,
            "Error": item.error,
            "Retrieved At": item.retrieved_at,
        }
        for item in health
    ]
    health_dir = output_dir / "health"
    write_csv(health_dir / f"source_health_{run_id_value}.csv", HEALTH_COLUMNS, rows)
    return write_csv(health_dir / "source_health_latest.csv", HEALTH_COLUMNS, rows)


def is_newly_posted(result: JobResult, today: date | None = None) -> bool:
    if not result.posted_date:
        return True
    try:
        posted = date.fromisoformat(result.posted_date)
    except ValueError:
        return True
    return posted >= (today or date.today()) - timedelta(days=NEWLY_POSTED_DAYS)


def write_run_report(output_dir: Path, run_id_value: str, categories: list[Category], buckets: Any, new_rows: dict[str, list[JobResult]], health: list[BoardHealth], stats: dict[str, Any]) -> tuple[Path, Path]:
    reports_dir = output_dir / "reports"
    logs_dir = output_dir / "logs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    status_counts = Counter(item.status for item in health)
    summary: dict[str, Any] = {
        "run_id": run_id_value,
        **{k: v for k, v in stats.items() if not k.startswith("_")},
        "boards_total": len(health),
        "board_status": dict(status_counts),
        "categories": {},
        "adjacent_roles": len(buckets.adjacent),
        "aggregator_review": len(buckets.aggregator),
    }
    for category in categories:
        current = buckets.main.get(category.id, [])
        summary["categories"][category.id] = {
            "current_matches": len(current),
            "new_matches": len(new_rows.get(category.id, [])),
            "high_confidence": sum(r.quality_tier == "high_confidence" for r in current),
            "needs_review": sum(r.quality_tier != "high_confidence" for r in current),
            "possible_matches": len(buckets.possible.get(category.id, [])),
            "overflow": len(buckets.overflow.get(category.id, [])),
        }
    json_path = logs_dir / f"run_{run_id_value}.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Job Scraper Daily Summary",
        "",
        f"- Run ID: `{run_id_value}` - duration `{stats.get('duration_s', '?')} s`",
        f"- Boards: `{len(health)}` ({', '.join(f'{k} {v}' for k, v in sorted(status_counts.items()))})",
        f"- Raw jobs collected: `{stats.get('raw_jobs', 0)}`; previously seen jobs missing today: `{stats.get('newly_missing', 0)}`",
        "",
        "| Category | Current | New today | High confidence | Needs review | Possible | Overflow |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category in categories:
        item = summary["categories"][category.id]
        lines.append(
            f"| {category.name} | {item['current_matches']} | {item['new_matches']} | {item['high_confidence']} | "
            f"{item['needs_review']} | {item['possible_matches']} | {item['overflow']} |"
        )
    lines += [
        "",
        f"- Related roles (`related_roles.csv`): `{len(buckets.adjacent)}` - Job-board finds (`job_board_finds.csv`): `{len(buckets.aggregator)}`",
    ]

    all_new = [(category, row) for category in categories for row in new_rows.get(category.id, [])]
    posted = [(c, r) for c, r in all_new if is_newly_posted(r)]
    surfaced = [(c, r) for c, r in all_new if not is_newly_posted(r)]
    for heading, rows in (("New today - newly posted", posted), ("New today - newly surfaced (posted > 7 days ago)", surfaced)):
        if not rows:
            continue
        lines += ["", f"## {heading} ({len(rows)})", "", "| Category | Company | Role | Experience | Location | Posted | Link |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for category, row in rows[:60]:
            lines.append(
                f"| {category.name} | {_md(row.company)} | {_md(row.title)} | {_md(row.experience_required)} | "
                f"{_md(row.location)[:40]} | {row.posted_date or '-'} | [open]({row.url}) |"
            )

    canaries = stats.get("_canaries") or []
    failed_canaries = [c for c in canaries if c.get("status") == "fail"]
    if failed_canaries:
        lines += ["", "## Link check failures (possible broken link format)"]
        lines += [f"- {c['source']}: {c['reason']} - {c['url']}" for c in failed_canaries]
    llm = stats.get("_llm") or {}
    if llm:
        lines += ["", "## Claude"]
        lines += [f"- {key}: {value}" for key, value in llm.items()]
    failed = [item for item in health if item.status in ("failed", "quarantined", "partial")]
    if failed:
        lines += ["", "## Sources needing attention"]
        for item in failed[:40]:
            detail = item.error or item.note
            lines.append(f"- {item.company} ({item.source}) - **{item.status}** {('- ' + detail[:160]) if detail else ''}")
    summary_path = reports_dir / "daily_summary_latest.md"
    text = "\n".join(lines) + "\n"
    summary_path.write_text(text, encoding="utf-8")
    (reports_dir / f"daily_summary_{run_id_value}.md").write_text(text, encoding="utf-8")
    return json_path, summary_path


def _md(value: str) -> str:
    return (value or "").replace("|", "/").replace("\n", " ").strip()
