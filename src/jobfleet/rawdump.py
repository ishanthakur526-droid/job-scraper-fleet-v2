"""Raw job dumps (gzip JSON lines) so classification can be replayed offline."""

from __future__ import annotations

import dataclasses
import gzip
import json
import time
from pathlib import Path
from typing import Any

from .models import BoardHealth, RawJob, utc_now_iso

_RAW_FIELDS = {f.name for f in dataclasses.fields(RawJob)}
_HEALTH_FIELDS = {f.name for f in dataclasses.fields(BoardHealth)}


def write_dump(path: Path, run_id: str, jobs: list[RawJob], health: list[BoardHealth]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "meta", "run_id": run_id, "created_at": utc_now_iso(), "version": 3}) + "\n")
        for item in health:
            handle.write(json.dumps({"type": "health", **dataclasses.asdict(item)}) + "\n")
        for job in jobs:
            handle.write(json.dumps({"type": "job", **dataclasses.asdict(job)}) + "\n")
    tmp.replace(path)
    return path


def read_dump(path: Path) -> tuple[dict[str, Any], list[RawJob], list[BoardHealth]]:
    meta: dict[str, Any] = {}
    jobs: list[RawJob] = []
    health: list[BoardHealth] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            kind = record.pop("type", "")
            if kind == "meta":
                meta = record
            elif kind == "health":
                health.append(BoardHealth(**{k: v for k, v in record.items() if k in _HEALTH_FIELDS}))
            elif kind == "job":
                jobs.append(RawJob(**{k: v for k, v in record.items() if k in _RAW_FIELDS}))
    return meta, jobs, health


def prune_dumps(directory: Path, keep_days: int = 14) -> int:
    if not directory.exists():
        return 0
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for path in directory.glob("*.jsonl.gz"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
