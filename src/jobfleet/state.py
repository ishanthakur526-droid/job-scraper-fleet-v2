"""Persistent run state (stdlib sqlite3).

Replaces the v2 ``job_history.csv`` as the source of truth. Unlike CSV it is
atomic and cannot be locked by Excel. CSV views are still exported for humans,
best-effort. Keys are stable ATS ids (``source:id``); old URL-based keys are
migrated through ``legacy_keys``/aliases so known jobs are not re-flagged new.
"""

from __future__ import annotations

import csv
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import BoardHealth, JobResult, RawJob

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
HARD_FAILURE_LIMIT = 3
QUARANTINE_DAYS = 14
PRUNE_INACTIVE_DAYS = 180

HISTORY_COLUMNS = [
    "Job Key", "First Seen At", "Last Seen At", "Seen Count", "Active", "Missing Since", "Last Missing At",
    "Missing Count", "Category", "Route", "Company", "Exact Role Name", "Experience Required", "Application Link",
    "Source", "Board", "Location", "Posted Date", "Quality Tier", "Score",
]

_JOB_COLUMNS = (
    "key", "first_seen", "last_seen", "seen_count", "active", "missing_since", "last_missing_at", "missing_count",
    "category", "route", "company", "title", "experience", "url", "source", "board_key", "location",
    "posted_date", "tier", "score",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self._create()
        self._claimed: dict[str, str] = {}

    # ------------------------------------------------------------- schema
    def _create(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS jobs (
                key TEXT PRIMARY KEY, first_seen TEXT, last_seen TEXT, seen_count INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1, missing_since TEXT DEFAULT '', last_missing_at TEXT DEFAULT '',
                missing_count INTEGER DEFAULT 0, category TEXT, route TEXT, company TEXT, title TEXT,
                experience TEXT, url TEXT, source TEXT, board_key TEXT DEFAULT '', location TEXT DEFAULT '',
                posted_date TEXT DEFAULT '', tier TEXT, score INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, key TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS boards (
                board_key TEXT PRIMARY KEY, consecutive_hard_failures INTEGER DEFAULT 0, last_status TEXT,
                last_error TEXT, last_ok TEXT, last_attempt TEXT, quarantined_until TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS probe_cache (key TEXT PRIMARY KEY, status TEXT, checked_at TEXT, detail TEXT);
            CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, kind TEXT, payload TEXT, created_at TEXT);
            """
        )
        if self.get_meta("schema_version") is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
        self.db.commit()

    def close(self) -> None:
        self.db.commit()
        self.db.close()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return row["v"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, value))
        self.db.commit()

    # ---------------------------------------------------- legacy import
    def import_legacy_history(self, csv_path: Path) -> int:
        """One-time import of a v2 ``job_history.csv`` (backed up first)."""
        if self.get_meta("legacy_import_done") or not csv_path.exists():
            return 0
        backup = csv_path.with_name("job_history.v2_backup.csv")
        if not backup.exists():
            shutil.copy2(csv_path, backup)
        count = 0
        with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                key = (row.get("Job Key") or "").strip()
                if not key:
                    continue
                self.db.execute(
                    """INSERT OR IGNORE INTO jobs (key, first_seen, last_seen, seen_count, active, missing_since,
                       last_missing_at, missing_count, category, route, company, title, experience, url, source,
                       board_key, location, posted_date, tier, score)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        key, row.get("First Seen At", ""), row.get("Last Seen At", ""), _int(row.get("Seen Count")),
                        1 if (row.get("Active") or "").lower() == "yes" else 0, row.get("Missing Since", ""),
                        row.get("Last Missing At", ""), _int(row.get("Missing Count")), row.get("Category", ""), "main",
                        row.get("Company", ""), row.get("Exact Role Name", ""), row.get("Experience Required", ""),
                        row.get("Application Link", ""), row.get("Source", ""), "", "", "", row.get("Quality Tier", ""), 0,
                    ),
                )
                count += 1
        self.set_meta("legacy_import_done", _iso(_now()))
        self.db.commit()
        log.info("Imported %s rows from legacy %s (backup: %s)", count, csv_path.name, backup.name)
        return count

    # ------------------------------------------------------------- jobs
    def _row(self, key: str) -> sqlite3.Row | None:
        if not key:
            return None
        row = self.db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
        if row:
            return row
        alias = self.db.execute("SELECT key FROM aliases WHERE alias=?", (key,)).fetchone()
        if alias:
            return self.db.execute("SELECT * FROM jobs WHERE key=?", (alias["key"],)).fetchone()
        return None

    def _claim(self, primary: str, legacy_keys: Iterable[str]) -> sqlite3.Row | None:
        """Find the row for ``primary``; else migrate the first unclaimed legacy row to it."""
        row = self._row(primary)
        if row is not None and self._claimed.get(row["key"], primary) == primary:
            self._claimed[row["key"]] = primary
            return row
        for legacy in legacy_keys:
            old = self._row(legacy)
            if old is None or old["key"] in self._claimed:
                continue
            if old["key"] != primary:
                if self._row(primary) is None:
                    self.db.execute("UPDATE jobs SET key=? WHERE key=?", (primary, old["key"]))
                    self.db.execute("UPDATE aliases SET key=? WHERE key=?", (primary, old["key"]))
                self.db.execute("INSERT OR REPLACE INTO aliases(alias, key) VALUES(?, ?)", (old["key"], primary))
            self._claimed[primary] = primary
            return self._row(primary)
        return None

    def record_results(self, results: list[JobResult], now: datetime | None = None) -> int:
        """Upsert accepted rows; sets ``is_new``/``first_seen`` on each result. Returns new count."""
        stamp = _iso(now or _now())
        new_count = 0
        for result in results:
            keys = result.all_keys()
            existing = [self._claim(key, result.legacy_keys if key == result.key else []) for key in keys]
            known = [row for row in existing if row is not None]
            result.is_new = not known
            result.first_seen = min((row["first_seen"] for row in known if row["first_seen"]), default=stamp)
            new_count += int(result.is_new)
            for key, row in zip(keys, existing, strict=True):
                self._upsert(key, row, result, stamp)
        self.db.commit()
        return new_count

    def _upsert(self, key: str, row: sqlite3.Row | None, result: JobResult, stamp: str) -> None:
        values = dict(
            category=result.category_id, route=result.route, company=result.company, title=result.title,
            experience=result.experience_required, url=result.url, source=result.source, board_key=result.board_key,
            location=result.location, posted_date=result.posted_date, tier=result.quality_tier, score=result.score,
        )
        if row is None:
            self.db.execute(
                f"INSERT OR IGNORE INTO jobs ({', '.join(_JOB_COLUMNS)}) VALUES ({', '.join('?' * len(_JOB_COLUMNS))})",
                (key, stamp, stamp, 1, 1, "", "", 0, *values.values()),
            )
            return
        self.db.execute(
            """UPDATE jobs SET last_seen=?, seen_count=seen_count+1, active=1, missing_since='', last_missing_at='',
               missing_count=0, category=?, route=?, company=?, title=?, experience=?, url=?, source=?, board_key=?,
               location=?, posted_date=?, tier=?, score=? WHERE key=?""",
            (stamp, *values.values(), row["key"]),
        )

    def mark_presence(
        self,
        raw_jobs: list[RawJob],
        succeeded_boards: set[str],
        succeeded_sources: set[str],
        now: datetime | None = None,
    ) -> int:
        """Refresh live jobs and mark absent ones missing. Returns jobs newly missing this run.

        A job only goes missing when its board (or, for imported rows without a
        board, every board of its source) succeeded today - so outages never
        masquerade as expired jobs.
        """
        stamp = _iso(now or _now())
        present: set[str] = set()
        for job in raw_jobs:
            present.add(job.key())
            present.update(job.all_legacy_keys())
        alias_targets = {
            row["alias"]: row["key"] for row in self.db.execute("SELECT alias, key FROM aliases").fetchall()
        }
        present |= {alias_targets[k] for k in list(present) if k in alias_targets}
        newly_missing = 0
        for row in self.db.execute("SELECT key, board_key, source, active, missing_since, missing_count FROM jobs").fetchall():
            if row["key"] in present:
                if not row["active"]:
                    self.db.execute(
                        "UPDATE jobs SET active=1, missing_since='', last_missing_at='', missing_count=0, last_seen=? WHERE key=?",
                        (stamp, row["key"]),
                    )
                else:
                    self.db.execute("UPDATE jobs SET last_seen=? WHERE key=?", (stamp, row["key"]))
                continue
            board_ok = row["board_key"] in succeeded_boards if row["board_key"] else row["source"] in succeeded_sources
            if not board_ok:
                continue
            if row["active"]:
                newly_missing += 1
            self.db.execute(
                """UPDATE jobs SET active=0, missing_since=CASE WHEN missing_since='' THEN ? ELSE missing_since END,
                   last_missing_at=?, missing_count=missing_count+1 WHERE key=?""",
                (stamp, stamp, row["key"]),
            )
        self.db.commit()
        return newly_missing

    def prune(self, days: int = PRUNE_INACTIVE_DAYS, now: datetime | None = None) -> int:
        cutoff = _iso((now or _now()) - timedelta(days=days))
        cursor = self.db.execute("DELETE FROM jobs WHERE active=0 AND last_seen < ? AND last_seen != ''", (cutoff,))
        self.db.execute("DELETE FROM aliases WHERE key NOT IN (SELECT key FROM jobs)")
        self.db.commit()
        return cursor.rowcount

    def counts(self) -> dict[str, int]:
        row = self.db.execute("SELECT COUNT(*) AS n, SUM(active) AS a FROM jobs").fetchone()
        return {"total": int(row["n"] or 0), "active": int(row["a"] or 0)}

    # ----------------------------------------------------------- boards
    def quarantined(self, now: datetime | None = None) -> dict[str, str]:
        stamp = _iso(now or _now())
        rows = self.db.execute(
            "SELECT board_key, quarantined_until FROM boards WHERE quarantined_until != '' AND quarantined_until > ?", (stamp,)
        ).fetchall()
        return {row["board_key"]: row["quarantined_until"] for row in rows}

    def update_board(self, health: BoardHealth, now: datetime | None = None) -> None:
        current = now or _now()
        stamp = _iso(current)
        row = self.db.execute("SELECT * FROM boards WHERE board_key=?", (health.board_key,)).fetchone()
        failures = int(row["consecutive_hard_failures"]) if row else 0
        last_ok = row["last_ok"] if row else ""
        quarantined_until = ""
        if health.status in ("ok", "empty", "partial"):
            failures, last_ok = 0, stamp
        elif health.status == "failed" and health.hard_failure:
            failures += 1
            if failures >= HARD_FAILURE_LIMIT:
                quarantined_until = _iso(current + timedelta(days=QUARANTINE_DAYS))
        elif row:
            quarantined_until = ""
        if health.status == "quarantined":
            return
        self.db.execute(
            """INSERT INTO boards(board_key, consecutive_hard_failures, last_status, last_error, last_ok, last_attempt,
               quarantined_until) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(board_key) DO UPDATE SET consecutive_hard_failures=excluded.consecutive_hard_failures,
               last_status=excluded.last_status, last_error=excluded.last_error, last_ok=excluded.last_ok,
               last_attempt=excluded.last_attempt, quarantined_until=excluded.quarantined_until""",
            (health.board_key, failures, health.status, health.error[:500], last_ok or "", stamp, quarantined_until),
        )
        self.db.commit()

    # ----------------------------------------------------------- caches
    def cache_get(self, table: str, key: str, max_age_days: float | None = None) -> dict[str, Any] | None:
        assert table in ("probe_cache", "llm_cache")
        column = "checked_at" if table == "probe_cache" else "created_at"
        row = self.db.execute(f"SELECT * FROM {table} WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        if max_age_days is not None:
            try:
                age = _now() - datetime.fromisoformat(row[column])
            except (TypeError, ValueError):
                return None
            if age > timedelta(days=max_age_days):
                return None
        return dict(row)

    def probe_put(self, key: str, status: str, detail: str = "") -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO probe_cache(key, status, checked_at, detail) VALUES(?,?,?,?)",
            (key, status, _iso(_now()), detail[:500]),
        )
        self.db.commit()

    def llm_put(self, key: str, kind: str, payload: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO llm_cache(key, kind, payload, created_at) VALUES(?,?,?,?)",
            (key, kind, json.dumps(payload), _iso(_now())),
        )
        self.db.commit()

    def llm_get(self, key: str, max_age_days: float = 60) -> dict[str, Any] | None:
        row = self.cache_get("llm_cache", key, max_age_days)
        return json.loads(row["payload"]) if row else None

    # ---------------------------------------------------------- exports
    def export_csv_views(self, state_dir: Path, output_dir: Path | None = None) -> list[Path]:
        from .exporters import write_csv  # local import to avoid a cycle

        rows = [dict(row) for row in self.db.execute("SELECT * FROM jobs ORDER BY key").fetchall()]
        history = [_history_row(row) for row in rows]
        written = []
        if output_dir is not None:
            # The rolling ledger for people: every job ever listed, most recently seen first, opens cleanly in Excel.
            ledger = sorted(history, key=lambda r: (r["Last Seen At"] or "", r["First Seen At"] or ""), reverse=True)
            written.append(write_csv(output_dir / "job_history.csv", LEDGER_COLUMNS, map(_ledger_row, ledger)))
        written += [
            write_csv(state_dir / "job_history.csv", HISTORY_COLUMNS, history, bom=False),
            write_csv(
                state_dir / "expired_or_missing_jobs.csv",
                HISTORY_COLUMNS,
                [row for row in history if row["Active"] == "no"],
                bom=False,
            ),
        ]
        return [path for path in written if path is not None]


LEDGER_COLUMNS = [
    "Still Open", "Company", "Exact Role Name", "Family", "Location", "Experience Required", "Application Link",
    "First Seen", "Last Seen", "Posted", "Tier", "Score", "Source",
]


def _ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "Still Open": "yes" if row["Active"] == "yes" else "no",
        "Company": row["Company"], "Exact Role Name": row["Exact Role Name"], "Family": row["Category"],
        "Location": row["Location"], "Experience Required": row["Experience Required"], "Application Link": row["Application Link"],
        "First Seen": (row["First Seen At"] or "")[:10], "Last Seen": (row["Last Seen At"] or "")[:10],
        "Posted": row["Posted Date"], "Tier": row["Quality Tier"], "Score": row["Score"], "Source": row["Source"],
    }


def _history_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "Job Key": row["key"], "First Seen At": row["first_seen"], "Last Seen At": row["last_seen"],
        "Seen Count": row["seen_count"], "Active": "yes" if row["active"] else "no",
        "Missing Since": row["missing_since"], "Last Missing At": row["last_missing_at"],
        "Missing Count": row["missing_count"], "Category": row["category"], "Route": row["route"],
        "Company": row["company"], "Exact Role Name": row["title"], "Experience Required": row["experience"],
        "Application Link": row["url"], "Source": row["source"], "Board": row["board_key"],
        "Location": row["location"], "Posted Date": row["posted_date"], "Quality Tier": row["tier"], "Score": row["score"],
    }


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
