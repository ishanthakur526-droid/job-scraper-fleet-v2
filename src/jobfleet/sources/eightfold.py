"""Eightfold-powered career sites (``/api/pcsx``), e.g. Microsoft.

Token: ``host|domain`` (``apply.careers.microsoft.com|microsoft.com``).
Options: ``queries`` (list of search strings), ``location`` (default India).
"""

from __future__ import annotations

from urllib.parse import urlencode

from ..http import FetchError
from ..models import Board, RawJob
from ..text import clean_html, normalize_space
from .base import SourceAdapter, epoch_to_date

PAGE_SIZE = 20


class EightfoldAdapter(SourceAdapter):
    name = "eightfold"

    def list_jobs(self, board: Board) -> list[RawJob]:
        host, domain = board.token.split("|", 1)
        queries = list(board.options.get("queries") or ["data analyst", "business analyst", "research analyst"])
        location = str(board.options.get("location", "India"))
        pages = int(board.options.get("pages", 2))
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for query in queries:
            for page in range(pages):
                if not self.time_left():
                    return jobs
                params = urlencode({"domain": domain, "query": query, "location": location, "start": page * PAGE_SIZE, "num": PAGE_SIZE})
                data = self.http.get_json(f"https://{host}/api/pcsx/search?{params}")
                payload = (data.get("data") or {}) if isinstance(data, dict) else {}
                positions = [p for p in payload.get("positions") or [] if isinstance(p, dict)]
                for position in positions:
                    pid = str(position.get("id") or "")
                    if pid and pid not in seen:
                        seen.add(pid)
                        jobs.append(self._job(board, host, domain, position))
                if len(positions) < PAGE_SIZE:
                    break
        return jobs

    def _job(self, board: Board, host: str, domain: str, position: dict) -> RawJob:
        pid = str(position.get("id"))
        title = normalize_space(position.get("name", ""))
        flags: dict = {}
        keep, reason = self.keep(title, flags)
        description = ""
        if keep and self.time_left():
            try:
                data = self.http.get_json(f"https://{host}/api/pcsx/position_details?{urlencode({'position_id': pid, 'domain': domain, 'hl': 'en'})}")
                detail = (data.get("data") or {}) if isinstance(data, dict) else {}
                description = clean_html(str(detail.get("jobDescription") or detail.get("description") or ""))
            except FetchError:
                description = ""
        elif not keep:
            flags["prefilter"] = reason
        locations = [normalize_space(str(x)) for x in position.get("locations") or [] if x]
        path = str(position.get("positionUrl") or f"/careers/job/{pid}")
        return RawJob(
            company=board.company,
            title=title,
            location="; ".join(locations),
            url=f"https://{host}{path}" if path.startswith("/") else path,
            description=description,
            source=self.name,
            source_id=str(position.get("displayJobId") or pid),
            stable_key=f"eightfold:{domain}:{pid}".lower(),
            posted_at=str(position.get("postedTs", "")),
            posted_date=epoch_to_date(position.get("postedTs")),
            locations=locations,
            flags=flags,
            url_kind="api",
        )
