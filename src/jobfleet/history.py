from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .models import JobResult


HISTORY_COLUMNS = [
    "Job Key",
    "First Seen At",
    "Last Seen At",
    "Seen Count",
    "Active",
    "Missing Since",
    "Last Missing At",
    "Missing Count",
    "Category",
    "Company",
    "Exact Role Name",
    "Experience Required",
    "Application Link",
    "Source",
    "Quality Tier",
]


def mark_new_jobs(state_dir: Path, buckets: dict[str, list[JobResult]]) -> dict[str, list[JobResult]]:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "job_history.csv"
    now = datetime.now(timezone.utc).isoformat()
    history = _read_history(path)
    new_by_category: dict[str, list[JobResult]] = {}
    current_keys = set()

    for category_id, results in buckets.items():
        new_by_category[category_id] = []
        for item in results:
            key = job_key(item)
            current_keys.add(key)
            existing = history.get(key)
            item.is_new = existing is None
            if item.is_new:
                new_by_category[category_id].append(item)
                first_seen = now
                seen_count = 1
            else:
                first_seen = existing["First Seen At"]
                seen_count = int(existing.get("Seen Count", "0") or "0") + 1

            history[key] = {
                "Job Key": key,
                "First Seen At": first_seen,
                "Last Seen At": now,
                "Seen Count": str(seen_count),
                "Active": "yes",
                "Missing Since": "",
                "Last Missing At": "",
                "Missing Count": "0",
                "Category": item.category_id,
                "Company": item.company,
                "Exact Role Name": item.title,
                "Experience Required": item.experience_required,
                "Application Link": item.url,
                "Source": item.source,
                "Quality Tier": item.quality_tier,
            }

    for key, row in history.items():
        if key in current_keys:
            continue
        missing_count = int(row.get("Missing Count", "0") or "0") + 1
        row["Active"] = "no"
        row["Missing Since"] = row.get("Missing Since") or now
        row["Last Missing At"] = now
        row["Missing Count"] = str(missing_count)

    _write_history(path, history)
    _write_missing_history(state_dir / "expired_or_missing_jobs.csv", history)
    return new_by_category


def job_key(item: JobResult) -> str:
    return item.url.split("?")[0].rstrip("/").lower()


def _read_history(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = {}
        for row in csv.DictReader(handle):
            if not row.get("Job Key"):
                continue
            for column in HISTORY_COLUMNS:
                row.setdefault(column, "")
            rows[row["Job Key"]] = row
        return rows


def _write_history(path: Path, history: dict[str, dict[str, str]]) -> None:
    try:
        _write_history_file(path, history)
    except PermissionError:
        _write_history_file(path.with_name("job_history_new.csv"), history)


def _write_history_file(path: Path, history: dict[str, dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
        writer.writeheader()
        for key in sorted(history):
            writer.writerow(history[key])


def _write_missing_history(path: Path, history: dict[str, dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
        writer.writeheader()
        for key in sorted(history):
            row = history[key]
            if row.get("Active") == "no":
                writer.writerow(row)
