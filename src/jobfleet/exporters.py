"""CSV outputs. Atomic writes; UTF-8 with BOM so Excel shows non-ASCII text
correctly; a file locked by Excel never aborts the run (``*_copy.csv`` fallback).

File names (per role family ``<id>``):
    <id>.csv                 every job that matches now (refreshed each run)
    <id>_new.csv             jobs first seen in this run
    overflow/<id>.csv        matches beyond the per-list caps
    worth_a_look/<id>.csv    borderline matches
    audit/<id>.csv           the main list with every diagnostic column
    audit/rejected_jobs.csv  every rejected job with the reason
"""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Any, Iterable

from .models import Category, JobResult, RejectedJob

log = logging.getLogger(__name__)

LEGACY_COLUMNS = ["Company", "Exact Role Name", "Experience Required", "Application Link", "System Notes"]
EXTRA_COLUMNS = ["Location", "Posted", "First Seen", "Tier", "Score", "Source"]
MAIN_COLUMNS = LEGACY_COLUMNS + EXTRA_COLUMNS
REVIEW_COLUMNS = MAIN_COLUMNS + ["Category"]
AUDIT_COLUMNS = MAIN_COLUMNS + [
    "Category", "Route", "Matched Terms", "Geo Basis", "Experience Evidence", "Review Flags", "Job Key", "Retrieved At",
]
REJECTION_COLUMNS = [
    "Company", "Exact Role Name", "Application Link", "Source", "Location", "Best Category", "Score", "Reason",
    "Stage", "Experience Required", "Matched Terms", "Geo Basis", "Job Key", "Retrieved At",
]


def write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]], bom: bool = True) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig" if bom else "utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    for target in (path, path.with_name(f"{path.stem}_copy{path.suffix}")):
        try:
            os.replace(tmp, target)
            if target != path:
                log.warning("%s is locked (open in Excel?); wrote %s instead", path.name, target.name)
            return target
        except PermissionError:
            continue
    tmp.unlink(missing_ok=True)
    log.error("Could not write %s (file locked)", path)
    return None


def main_row(item: JobResult) -> dict[str, Any]:
    return {
        "Company": item.company,
        "Exact Role Name": item.title,
        "Experience Required": item.experience_required,
        "Application Link": item.url,
        "System Notes": item.system_notes,
        "Location": item.location,
        "Posted": item.posted_date,
        "First Seen": (item.first_seen or "")[:10],
        "Tier": item.quality_tier,
        "Score": item.score,
        "Source": item.source,
        "Category": item.category_id,
    }


def audit_row(item: JobResult) -> dict[str, Any]:
    row = main_row(item)
    row.update(
        {
            "Route": item.route,
            "Matched Terms": "; ".join(item.matched_terms),
            "Geo Basis": item.geo_basis,
            "Experience Evidence": item.exp_evidence,
            "Review Flags": "; ".join(item.review_flags),
            "Job Key": item.key,
            "Retrieved At": item.retrieved_at,
        }
    )
    return row


RELATED_ROLES_FILE = "related_roles.csv"
JOB_BOARD_FINDS_FILE = "job_board_finds.csv"


def export_category(output_dir: Path, category: Category, results: list[JobResult]) -> tuple[Path | None, Path | None]:
    current = write_csv(output_dir / category.output, MAIN_COLUMNS, map(main_row, results))
    audit = write_csv(output_dir / "audit" / f"{category.id}.csv", AUDIT_COLUMNS, map(audit_row, results))
    return current, audit


def export_new_only(output_dir: Path, category: Category, results: list[JobResult]) -> Path | None:
    return write_csv(output_dir / f"{category.id}_new.csv", MAIN_COLUMNS, map(main_row, results))


def export_worth_a_look(output_dir: Path, category: Category, possible: list[JobResult]) -> Path | None:
    return write_csv(output_dir / "worth_a_look" / f"{category.id}.csv", MAIN_COLUMNS, map(main_row, possible))


def export_overflow(output_dir: Path, category: Category, results: list[JobResult]) -> Path | None:
    return write_csv(output_dir / "overflow" / f"{category.id}.csv", MAIN_COLUMNS, map(main_row, results))


def export_review_file(path: Path, results: list[JobResult]) -> Path | None:
    return write_csv(path, REVIEW_COLUMNS, map(main_row, results))


def export_rejected_jobs(output_dir: Path, rejected: list[RejectedJob]) -> Path | None:
    return write_csv(
        output_dir / "audit" / "rejected_jobs.csv",
        REJECTION_COLUMNS,
        (
            {
                "Company": item.company,
                "Exact Role Name": item.title,
                "Application Link": item.url,
                "Source": item.source,
                "Location": item.location,
                "Best Category": item.category_id,
                "Score": item.score,
                "Reason": item.reason,
                "Stage": item.stage,
                "Experience Required": item.experience_required,
                "Matched Terms": "; ".join(item.matched_terms),
                "Geo Basis": item.geo_basis,
                "Job Key": item.key,
                "Retrieved At": item.retrieved_at,
            }
            for item in rejected
        ),
    )
