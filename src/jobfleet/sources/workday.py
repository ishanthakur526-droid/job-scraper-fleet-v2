"""Workday CXS adapter.

Facts verified against live tenants (Nov 2026): ``limit`` above 20 returns
HTTP 400, ``total`` is only reported on the first page, the India country
facet id is the same across tenants but the facet name varies (nested
``locationMainGroup -> locationCountry`` or custom ``CF_...Country``), and
list items with ``locationsText`` like "2 Locations" need the detail call.
"""

from __future__ import annotations

import re
from typing import Any

from ..geo import classify_segment, resolve
from ..http import FetchError
from ..models import Board, RawJob, legacy_url_key
from ..text import clean_html, normalize_space
from .base import SourceAdapter, iso_date, relative_date

INDIA_COUNTRY_ID = "c4f78be1a8f14da0ab49ce1162348a5e"
PAGE_SIZE = 20


def parse_workday_token(token: str) -> tuple[str, str, str]:
    parts = token.split("|")
    if len(parts) != 3:
        raise ValueError("Workday token must be host|tenant|site")
    return parts[0], parts[1], parts[2]


class WorkdayAdapter(SourceAdapter):
    name = "workday"

    def list_jobs(self, board: Board) -> list[RawJob]:
        host, tenant, site = parse_workday_token(board.token)
        endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        headers = {"Origin": f"https://{host}", "Referer": f"https://{host}/en-US/{site}", "Content-Type": "application/json"}
        cap = int(board.options.get("max_jobs", 300))

        base_search = str(board.options.get("search_text", ""))
        first = self._post(endpoint, {}, 0, base_search, headers)
        facet_param, facet_ids, mode = find_india_facet(first.get("facets") or [])
        if facet_param:
            applied, search_text = {facet_param: facet_ids}, base_search
        else:
            applied, search_text, mode = {}, f"{base_search} India".strip(), "search"
        page = self._post(endpoint, applied, 0, search_text, headers)
        total = int(page.get("total") or 0)
        postings = [p for p in page.get("jobPostings") or [] if isinstance(p, dict)]
        offset = PAGE_SIZE
        while offset < min(total, cap) and self.time_left():
            more = [p for p in self._post(endpoint, applied, offset, search_text, headers).get("jobPostings") or [] if isinstance(p, dict)]
            if not more:
                break
            postings.extend(more)
            offset += PAGE_SIZE
        if mode != "search":
            self.notes.append(f"India facet {facet_param} ({mode}): {total} jobs")

        unique: dict[str, dict] = {}
        for item in postings[:cap]:
            path = str(item.get("externalPath") or "")
            if path and path not in unique:
                unique[path] = item
        india_filtered = mode == "country"
        return self.map_parallel(lambda item: self._job(board, host, tenant, site, item, india_filtered), list(unique.values()))

    def _post(self, endpoint: str, applied: dict, offset: int, search_text: str, headers: dict) -> dict[str, Any]:
        payload = {"appliedFacets": applied, "limit": PAGE_SIZE, "offset": offset, "searchText": search_text}
        data = self.http.post_json(endpoint, payload, headers=headers)
        return data if isinstance(data, dict) else {}

    def _job(self, board: Board, host: str, tenant: str, site: str, item: dict, india_filtered: bool) -> RawJob:
        path = str(item.get("externalPath") or "")
        title = normalize_space(item.get("title", ""))
        list_location = normalize_space(item.get("locationsText", "")) or _location_from_path(path)
        flags: dict = {}
        keep, reason = self.keep(title, flags)
        detail: dict = {}
        if keep and self.time_left():
            try:
                fetched = self.http.get_json(f"https://{host}/wday/cxs/{tenant}/{site}{path}")
                info = fetched.get("jobPostingInfo") if isinstance(fetched, dict) else None
                detail = info if isinstance(info, dict) else {}
            except FetchError:
                detail = {}
        elif not keep:
            flags["prefilter"] = reason
        req_id = str(detail.get("jobReqId") or _req_id_from_path(path) or path)
        legacy = f"https://{host}/en-US/{site}{path}"
        locations = [normalize_space(str(x)) for x in detail.get("additionalLocations") or [] if x]
        country = (detail.get("country") or {}).get("descriptor") if isinstance(detail.get("country"), dict) else ""
        trust_filter = india_filtered and resolve(list_location).status != "foreign"  # e.g. 'Colombo, Sri Lanka' rows
        codes = [str(country)] if country else (["IN"] if trust_filter else [])
        posted = detail.get("startDate") or ""
        return RawJob(
            company=board.company,
            title=normalize_space(detail.get("title") or title),
            location=normalize_space(detail.get("location") or list_location),
            url=detail.get("externalUrl") or legacy,
            description=clean_html(detail.get("jobDescription", "")),
            source=self.name,
            source_id=req_id,
            stable_key=f"workday:{tenant}:{req_id}".lower(),
            posted_at=str(posted or item.get("postedOn", "")),
            posted_date=iso_date(posted) or relative_date(str(item.get("postedOn", ""))),
            country_codes=codes,
            locations=locations,
            legacy_keys=[legacy_url_key(legacy)],
            flags=flags,
            url_kind="api" if detail.get("externalUrl") else "constructed",
        )


def _location_from_path(path: str) -> str:
    """'/job/Bengaluru-BDC9A/Title_R1' -> 'Bengaluru BDC9A' (used when locationsText is blank)."""
    match = re.match(r"/job/([^/]+)/", path or "")
    if not match or re.fullmatch(r"\d+-Locations?", match.group(1), flags=re.I):
        return ""
    return normalize_space(match.group(1).replace("---", "|").replace("-", " ").replace("|", " - "))


def _req_id_from_path(path: str) -> str:
    match = re.search(r"_([A-Za-z0-9-]+)$", path or "")
    return match.group(1) if match else ""


def find_india_facet(facets: list[dict]) -> tuple[str, list[str], str]:
    """Return (facetParameter, ids, mode) for the India filter, searching nested facets.

    mode is "country" when a country facet value for India was found, "locations"
    when India-resolving location values were found, and "" otherwise.
    """
    country_hit: tuple[str, list[str]] | None = None
    location_ids: dict[str, list[str]] = {}

    def walk(nodes: list, parent: str) -> None:
        nonlocal country_hit
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            param = str(node.get("facetParameter") or parent or "")
            values = node.get("values")
            if isinstance(values, list) and values and isinstance(values[0], dict) and "facetParameter" in values[0]:
                walk(values, param)
                continue
            for value in values or []:
                if not isinstance(value, dict):
                    continue
                if "values" in value and isinstance(value.get("values"), list):
                    walk([value], param)
                    continue
                descriptor = normalize_space(str(value.get("descriptor", "")))
                value_id = str(value.get("id", ""))
                if not value_id:
                    continue
                if value_id == INDIA_COUNTRY_ID or (descriptor.lower() == "india" and "country" in param.lower()):
                    if country_hit is None:
                        country_hit = (param, [value_id])
                elif "location" in param.lower() and classify_segment(descriptor)[0] == "india":
                    location_ids.setdefault(param, []).append(value_id)

    walk(facets, "")
    if country_hit:
        return country_hit[0], country_hit[1], "country"
    if location_ids:
        param, ids = max(location_ids.items(), key=lambda item: len(item[1]))
        return param, ids, "locations"
    return "", [], ""
