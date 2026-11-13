"""amazon.jobs public search JSON.

The public job id is ``id_icims`` and the canonical link is ``job_path``.
v2 built links from ``id`` (an internal UUID) which return HTTP 404; those old
links are kept as legacy keys so job history migrates instead of re-flagging.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from ..geo import iso3
from ..models import Board, RawJob, legacy_url_key
from ..text import clean_html, normalize_space
from .base import SourceAdapter, iso_date

BASE = "https://www.amazon.jobs"
PAGE_SIZE = 100


class AmazonJobsAdapter(SourceAdapter):
    name = "amazon_jobs"

    def list_jobs(self, board: Board) -> list[RawJob]:
        cap = int(board.options.get("max_jobs", 300))
        configured = board.options.get("country")
        countries = [str(configured)] if configured else [iso3(c) for c in self.ctx.countries] or [""]
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for country in countries:
            self._collect(board, country, cap, jobs, seen)
        return jobs

    def _collect(self, board: Board, country: str, cap: int, jobs: list[RawJob], seen: set[str]) -> None:
        offset = 0
        while offset < cap and self.time_left():
            params: dict = {"base_query": board.token}
            if country:
                params["country"] = country
            query = urlencode({**params, "offset": offset, "result_limit": PAGE_SIZE})
            data = self.http.get_json(f"{BASE}/en/search.json?{query}")
            data = data if isinstance(data, dict) else {}
            page = [item for item in data.get("jobs") or [] if isinstance(item, dict)]
            for item in page:
                job = self._job(board, item)
                if job and job.source_id not in seen:
                    seen.add(job.source_id)
                    jobs.append(job)
            hits = int(data.get("hits") or 0)
            offset += PAGE_SIZE
            if not page or offset >= hits:
                break

    def _job(self, board: Board, item: dict) -> RawJob | None:
        icims = str(item.get("id_icims") or "").strip()
        path = str(item.get("job_path") or "").strip() or (f"/en/jobs/{icims}" if icims else "")
        if not icims or not path:
            return None
        locations, codes = _locations(item)
        location = normalize_space(
            item.get("normalized_location") or ", ".join(p for p in (item.get("city"), item.get("country_code")) if p)
        )
        if item.get("country_code"):
            codes.insert(0, str(item["country_code"]))
        legacy = [legacy_url_key(f"{BASE}/en/jobs/{item['id']}")] if item.get("id") else []
        flags = {
            key: True
            for key, field_name in (("intern", "is_intern"), ("university", "university_job"), ("people_manager", "is_manager"))
            if item.get(field_name) is True
        }
        return RawJob(
            company=board.company,
            title=normalize_space(item.get("title", "")),
            location=location,
            url=f"{BASE}{path}" if path.startswith("/") else path,
            description=clean_html(item.get("description", "")),
            source=self.name,
            source_id=icims,
            stable_key=f"amazon_jobs:{icims}",
            posted_at=str(item.get("posted_date", "")),
            posted_date=iso_date(item.get("posted_date")),
            country_codes=codes,
            locations=locations,
            requirements_text=clean_html(item.get("basic_qualifications", "")),
            preferred_text=clean_html(item.get("preferred_qualifications", "")),
            legacy_keys=legacy,
            flags=flags,
            url_kind="api",
        )


def _locations(item: dict) -> tuple[list[str], list[str]]:
    names: list[str] = []
    codes: list[str] = []
    for raw in item.get("locations") or []:
        data = raw
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                names.append(normalize_space(raw))
                continue
        if isinstance(data, dict):
            name = data.get("normalizedLocation") or data.get("locationNonStemming") or data.get("city")
            if name:
                names.append(normalize_space(str(name)))
            code = data.get("countryIso2a") or data.get("normalizedCountryCode")
            if code:
                codes.append(str(code))
    return names, codes
