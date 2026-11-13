"""Write outputs/dashboard.html: one self-contained page (no internet needed) with
every list from a run, searchable and filterable. The same file is what cloud
mode publishes on GitHub Pages."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from .models import BoardHealth, JobResult
from .text import truncate


def _row(result: JobResult, family: str) -> dict[str, Any]:
    note = ""
    for part in (result.system_notes or "").split("; "):
        if part and not part.startswith("+") and "opening(s)" not in part:
            note = part
            break
    return {
        "title": result.title,
        "company": result.company,
        "location": truncate(result.location, 80),
        "experience": result.experience_required,
        "posted": result.posted_date,
        "first_seen": (result.first_seen or "")[:10],
        "tier": result.quality_tier,
        "score": result.score,
        "new": bool(result.is_new),
        "url": result.url,
        "family": family,
        "note": truncate(note, 140),
    }


def build_data(profile: Any, buckets: Any, health: list[BoardHealth], stats: dict[str, Any]) -> dict[str, Any]:
    names = {f.id: f.name for f in profile.families}
    families = []
    for family in profile.families:
        rows = list(buckets.main.get(family.id, [])) + list(buckets.overflow.get(family.id, []))
        families.append({"id": family.id, "name": family.name, "rows": [_row(r, family.name) for r in rows]})
    possible = [_row(r, names.get(r.category_id, r.category_id)) for rows in buckets.possible.values() for r in rows]
    return {
        "profile": {"name": profile.name, "describe": profile.describe()},
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run": {"raw_jobs": stats.get("raw_jobs", 0), "duration_s": stats.get("duration_s", 0)},
        "families": families,
        "adjacent": [_row(r, "Related") for r in buckets.adjacent],
        "possible": possible,
        "aggregator": [_row(r, names.get(r.category_id, "")) for r in buckets.aggregator],
        "sources": [
            {"company": h.company, "source": h.source, "status": h.status, "jobs": h.jobs_found, "seconds": round(h.duration_s, 1),
             "note": truncate(h.error or h.note, 160)}
            for h in sorted(health, key=lambda h: (h.status in ("ok", "empty"), h.company.lower()))
        ],
    }


def render(data: dict[str, Any]) -> str:
    template = (resources.files("jobfleet") / "data" / "dashboard.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace("/*__DATA__*/", payload)


def write_dashboard(output_dir: Path, profile: Any, buckets: Any, health: list[BoardHealth], stats: dict[str, Any]) -> Path:
    path = output_dir / "dashboard.html"
    tmp = path.with_suffix(".html.tmp")
    tmp.write_text(render(build_data(profile, buckets, health, stats)), encoding="utf-8")
    os.replace(tmp, path)
    return path
