from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from ..http import HttpClient
from ..models import Board, RawJob

Prefilter = Callable[[str, "dict | None"], "tuple[bool, str]"]


@dataclass
class AdapterContext:
    prefilter: Prefilter | None = None
    budget_s: float = 120.0
    options: dict[str, Any] = field(default_factory=dict)


class SourceAdapter:
    """Base class. Adapters must check ``time_left()`` inside loops (threads cannot be killed)."""

    name = ""

    def __init__(self, http: HttpClient, context: AdapterContext | None = None):
        self.http = http
        self.ctx = context or AdapterContext()
        self.partial = False
        self.notes: list[str] = []
        self._deadline = time.monotonic() + max(1.0, float(self.ctx.budget_s))

    def time_left(self) -> bool:
        if time.monotonic() < self._deadline:
            return True
        self.partial = True
        return False

    def keep(self, title: str, flags: dict | None = None) -> tuple[bool, str]:
        if self.ctx.prefilter is None:
            return True, ""
        return self.ctx.prefilter(title, flags)

    def map_parallel(self, func: Callable[[Any], Any], items: list[Any], workers: int = 3) -> list[Any]:
        """Run per-job detail fetches concurrently (the HTTP client enforces per-host limits)."""
        if workers <= 1 or len(items) <= 1:
            return [func(item) for item in items]
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"{self.name}-detail") as pool:
            return list(pool.map(func, items))

    def list_jobs(self, board: Board) -> list[RawJob]:  # pragma: no cover - interface
        raise NotImplementedError

    def fetch_url(self, url: str) -> RawJob | None:
        return None


_MONTHS = "january february march april may june july august september october november december".split()


def iso_date(value: Any) -> str:
    """Best-effort conversion of many date formats to YYYY-MM-DD ('' if unknown)."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return epoch_to_date(value)
    text = str(value).strip()
    if re.fullmatch(r"\d{10,13}", text):
        return epoch_to_date(int(text))
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    match = re.match(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", text)
    if match:
        month = _month_number(match.group(1))
        if month:
            return f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(2)):02d}"
    match = re.match(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", text)
    if match:
        month = _month_number(match.group(2))
        if month:
            return f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(1)):02d}"
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:  # assume M/D/YYYY (SuccessFactors US-style)
        try:
            return date(int(match.group(3)), int(match.group(1)), int(match.group(2))).isoformat()
        except ValueError:
            return ""
    return relative_date(text)


def _month_number(name: str) -> int:
    name = name.lower()[:3]
    for index, month in enumerate(_MONTHS, start=1):
        if month.startswith(name):
            return index
    return 0


def epoch_to_date(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number > 10_000_000_000:  # milliseconds
        number /= 1000
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def relative_date(text: str) -> str:
    """'Posted Today', 'Posted 3 Days Ago', 'Posted 30+ Days Ago' -> approximate date."""
    low = (text or "").lower()
    today = datetime.now(timezone.utc).date()
    if "today" in low or "just posted" in low:
        return today.isoformat()
    if "yesterday" in low:
        return (today - timedelta(days=1)).isoformat()
    match = re.search(r"(\d+)\+?\s*(day|week|month)s?\s*ago", low)
    if match:
        amount = int(match.group(1))
        days = amount * {"day": 1, "week": 7, "month": 30}[match.group(2)]
        return (today - timedelta(days=days)).isoformat()
    return ""
