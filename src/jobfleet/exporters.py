from __future__ import annotations

import csv
from pathlib import Path

from .models import Category, JobResult, RejectedJob


LEGACY_COLUMNS = ["Company", "Exact Role Name", "Experience Required", "Application Link", "System Notes"]
AUDIT_COLUMNS = LEGACY_COLUMNS + ["Category", "Score", "Source", "Location", "Matched Terms", "Retrieved At"]
REJECTION_COLUMNS = [
    "Company",
    "Exact Role Name",
    "Application Link",
    "Source",
    "Location",
    "Best Category",
    "Score",
    "Reason",
    "Experience Required",
    "Matched Terms",
    "Retrieved At",
]


def export_category(output_dir: Path, category: Category, results: list[JobResult]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    legacy_path = output_dir / category.output
    audit_path = output_dir / f"audit_{category.output}"

    legacy_path = _available_path(legacy_path)
    with legacy_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEGACY_COLUMNS)
        writer.writeheader()
        for item in results:
            writer.writerow(_legacy_row(item))

    audit_path = _available_path(audit_path)
    with audit_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_COLUMNS)
        writer.writeheader()
        for item in results:
            row = _legacy_row(item)
            row.update(
                {
                    "Category": item.category_id,
                    "Score": item.score,
                    "Source": item.source,
                    "Location": item.location,
                    "Matched Terms": "; ".join(item.matched_terms),
                    "Retrieved At": item.retrieved_at,
                }
            )
            writer.writerow(row)

    return legacy_path, audit_path


def export_new_only(output_dir: Path, category: Category, results: list[JobResult]) -> Path:
    path = _available_path(output_dir / f"new_only_{category.output}")
    _write_legacy(path, results)
    return path


def export_quality_tiers(output_dir: Path, category: Category, results: list[JobResult]) -> dict[str, Path]:
    tier_dir = output_dir / "quality_tiers"
    tier_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for tier in ("high_confidence", "needs_review"):
        path = _available_path(tier_dir / f"{tier}_{category.output}")
        _write_legacy(path, [item for item in results if item.quality_tier == tier])
        paths[tier] = path
    return paths


def export_possible_matches(output_dir: Path, category: Category, results: list[JobResult]) -> Path:
    tier_dir = output_dir / "quality_tiers"
    tier_dir.mkdir(parents=True, exist_ok=True)
    path = _available_path(tier_dir / f"possible_match_{category.output}")
    _write_legacy(path, results)
    return path


def export_rejected_jobs(output_dir: Path, rejected: list[RejectedJob]) -> Path:
    audit_dir = output_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = _available_path(audit_dir / "rejected_jobs_today.csv")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REJECTION_COLUMNS)
        writer.writeheader()
        for item in rejected:
            writer.writerow(
                {
                    "Company": item.company,
                    "Exact Role Name": item.title,
                    "Application Link": item.url,
                    "Source": item.source,
                    "Location": item.location,
                    "Best Category": item.category_id,
                    "Score": item.score,
                    "Reason": item.reason,
                    "Experience Required": item.experience_required,
                    "Matched Terms": "; ".join(item.matched_terms),
                    "Retrieved At": item.retrieved_at,
                }
            )
    return path


def _legacy_row(item: JobResult) -> dict[str, str]:
    return {
        "Company": item.company,
        "Exact Role Name": item.title,
        "Experience Required": item.experience_required,
        "Application Link": item.url,
        "System Notes": item.system_notes,
    }


def _write_legacy(path: Path, results: list[JobResult]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEGACY_COLUMNS)
        writer.writeheader()
        for item in results:
            writer.writerow(_legacy_row(item))


def _available_path(path: Path) -> Path:
    try:
        with path.open("a", newline="", encoding="utf-8"):
            pass
        return path
    except PermissionError:
        return path.with_name(f"{path.stem}_new{path.suffix}")
