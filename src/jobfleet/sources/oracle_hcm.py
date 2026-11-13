"""Oracle Recruiting Cloud (HCM) candidate-experience REST API (e.g. JPMorgan Chase).

Token: ``host|siteNumber``. Options: ``keywords`` (list), ``location`` (default India).
The ``finder=`` value is built by hand: its ';' and ',' separators must stay unencoded.
"""

from __future__ import annotations

from urllib.parse import quote

from ..http import FetchError
from ..models import Board, RawJob
from ..text import clean_html, normalize_space
from .base import SourceAdapter, iso_date

PAGE_SIZE = 25


class OracleHcmAdapter(SourceAdapter):
    name = "oracle_hcm"

    def list_jobs(self, board: Board) -> list[RawJob]:
        host, site = board.token.split("|", 1)
        keywords = list(board.options.get("keywords") or ["analyst"])
        location = str(board.options.get("location", "India"))
        cap = int(board.options.get("max_jobs", 200))
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for keyword in keywords:
            offset = 0
            while offset < cap and self.time_left():
                finder = (
                    f"findReqs;siteNumber={site},facetsList=LOCATIONS,limit={PAGE_SIZE},offset={offset},"
                    f"keyword={quote(chr(34) + keyword + chr(34))},location={quote(location)},sortBy=POSTING_DATES_DESC"
                )
                url = (
                    f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                    f"?onlyData=true&expand=requisitionList.secondaryLocations&finder={finder}"
                )
                data = self.http.get_json(url)
                items = (data.get("items") or []) if isinstance(data, dict) else []
                block = items[0] if items and isinstance(items[0], dict) else {}
                reqs = [r for r in block.get("requisitionList") or [] if isinstance(r, dict)]
                fresh = []
                for req in reqs:
                    req_id = str(req.get("Id") or "")
                    if req_id and req_id not in seen:
                        seen.add(req_id)
                        fresh.append(req)
                jobs.extend(self.map_parallel(lambda req: self._job(board, host, site, req), fresh))
                total = int(block.get("TotalJobsCount") or 0)
                offset += PAGE_SIZE
                if not reqs or offset >= total:
                    break
        return jobs

    def _job(self, board: Board, host: str, site: str, req: dict) -> RawJob:
        req_id = str(req.get("Id"))
        title = normalize_space(req.get("Title", ""))
        flags: dict = {}
        keep, reason = self.keep(title, flags)
        detail: dict = {}
        if keep and self.time_left():
            try:
                url = (
                    f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
                    f"?expand=all&onlyData=true&finder=ById;Id={quote(chr(34) + req_id + chr(34))},siteNumber={site}"
                )
                data = self.http.get_json(url)
                items = data.get("items") if isinstance(data, dict) else None
                detail = items[0] if items and isinstance(items[0], dict) else {}
            except FetchError:
                detail = {}
        elif not keep:
            flags["prefilter"] = reason
        secondary = [
            normalize_space(str(loc.get("Name") or ""))
            for loc in req.get("secondaryLocations") or []
            if isinstance(loc, dict) and loc.get("Name")
        ]
        codes = [str(req["PrimaryLocationCountry"])] if req.get("PrimaryLocationCountry") else []
        codes += [str(loc["CountryCode"]) for loc in req.get("secondaryLocations") or [] if isinstance(loc, dict) and loc.get("CountryCode")]
        description = "\n".join(
            clean_html(str(detail.get(key) or ""))
            for key in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr")
            if detail.get(key)
        ) or clean_html(str(req.get("ShortDescriptionStr") or ""))
        return RawJob(
            company=board.company,
            title=title,
            location=normalize_space(req.get("PrimaryLocation", "")),
            url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{req_id}",
            description=description,
            source=self.name,
            source_id=req_id,
            stable_key=f"oracle_hcm:{host.split('.')[0]}:{req_id}".lower(),
            posted_at=str(req.get("PostedDate", "")),
            posted_date=iso_date(req.get("PostedDate")),
            country_codes=codes,
            locations=secondary,
            requirements_text=clean_html(str(detail.get("ExternalQualificationsStr") or "")),
            flags=flags,
            url_kind="constructed",
        )
