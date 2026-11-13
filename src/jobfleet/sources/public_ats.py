from __future__ import annotations

from urllib.parse import urlencode

from ..http import FetchError
from ..models import Board, RawJob, legacy_url_key
from ..text import clean_html, normalize_block, normalize_space
from .base import SourceAdapter, epoch_to_date, iso_date


class LeverAdapter(SourceAdapter):
    name = "lever"

    def list_jobs(self, board: Board) -> list[RawJob]:
        host = "api.eu.lever.co" if board.options.get("eu") else "api.lever.co"
        params = urlencode({"mode": "json", **dict(board.options.get("params") or {})})
        data = self.http.get_json(f"https://{host}/v0/postings/{board.token}?{params}", timeout=board.options.get("timeout"))
        if not isinstance(data, list):
            return []
        jobs: list[RawJob] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            categories = item.get("categories") or {}
            all_locations = [normalize_space(str(x)) for x in categories.get("allLocations") or [] if x]
            location = normalize_space(categories.get("location") or ", ".join(all_locations))
            parts = [item.get("descriptionPlain") or clean_html(item.get("description", ""))]
            for block in item.get("lists") or []:
                if isinstance(block, dict):  # requirement bullets live in lists[].content
                    parts.append(f"{block.get('text', '')}:\n{clean_html(block.get('content', ''))}")
            parts.append(item.get("additionalPlain") or clean_html(item.get("additional", "")))
            job_id = str(item.get("id", ""))
            url = item.get("hostedUrl") or f"https://jobs.lever.co/{board.token}/{job_id}"
            jobs.append(
                RawJob(
                    company=board.company,
                    title=normalize_space(item.get("text", "")),
                    location=location,
                    url=url,
                    description=normalize_block("\n".join(p for p in parts if p)),
                    source=self.name,
                    source_id=job_id,
                    posted_at=str(item.get("createdAt", "")),
                    posted_date=epoch_to_date(item.get("createdAt")),
                    country_codes=[str(item["country"])] if item.get("country") else [],
                    locations=all_locations,
                    url_kind="api",
                )
            )
        return jobs


class GreenhouseAdapter(SourceAdapter):
    name = "greenhouse"

    def list_jobs(self, board: Board) -> list[RawJob]:
        host = "boards-api.eu.greenhouse.io" if board.options.get("eu") else "boards-api.greenhouse.io"
        data = self.http.get_json(f"https://{host}/v1/boards/{board.token}/jobs?content=true")
        jobs: list[RawJob] = []
        for item in (data or {}).get("jobs", []) if isinstance(data, dict) else []:
            offices = [
                normalize_space(str(office.get("location") or office.get("name") or ""))
                for office in item.get("offices") or []
                if isinstance(office, dict)
            ]
            job_id = str(item.get("id", ""))
            posted = item.get("first_published") or item.get("updated_at") or ""
            jobs.append(
                RawJob(
                    company=board.company,
                    title=normalize_space(item.get("title", "")),
                    location=normalize_space((item.get("location") or {}).get("name", "")),
                    url=item.get("absolute_url") or f"https://job-boards.greenhouse.io/{board.token}/jobs/{job_id}",
                    description=clean_html(item.get("content", "")),
                    source=self.name,
                    source_id=job_id,
                    posted_at=str(posted),
                    posted_date=iso_date(posted),
                    locations=[office for office in offices if office],
                    url_kind="api",
                )
            )
        return jobs


class AshbyAdapter(SourceAdapter):
    name = "ashby"

    def list_jobs(self, board: Board) -> list[RawJob]:
        data = self.http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board.token}?includeCompensation=false")
        jobs: list[RawJob] = []
        for item in (data or {}).get("jobs", []) if isinstance(data, dict) else []:
            if item.get("isListed") is False:
                continue
            codes: list[str] = []
            locations: list[str] = []
            address = ((item.get("address") or {}).get("postalAddress") or {})
            if address.get("addressCountry"):
                codes.append(str(address["addressCountry"]))
            for secondary in item.get("secondaryLocations") or []:
                if not isinstance(secondary, dict):
                    continue
                if secondary.get("location"):
                    locations.append(normalize_space(str(secondary["location"])))
                postal = ((secondary.get("address") or {}).get("postalAddress") or {})
                if postal.get("addressCountry"):
                    codes.append(str(postal["addressCountry"]))
            description = item.get("descriptionPlain") or clean_html(item.get("descriptionHtml", ""))
            job_id = str(item.get("id", ""))
            jobs.append(
                RawJob(
                    company=board.company,
                    title=normalize_space(item.get("title", "")),
                    location=normalize_space(item.get("location", "")),
                    url=item.get("jobUrl") or item.get("applyUrl") or f"https://jobs.ashbyhq.com/{board.token}/{job_id}",
                    description=normalize_block(description),
                    source=self.name,
                    source_id=job_id,
                    posted_at=str(item.get("publishedAt", "")),
                    posted_date=iso_date(item.get("publishedAt")),
                    country_codes=codes,
                    locations=locations,
                    url_kind="api",
                )
            )
        return jobs


class SmartRecruitersAdapter(SourceAdapter):
    name = "smartrecruiters"
    PAGE = 100

    def list_jobs(self, board: Board) -> list[RawJob]:
        token = board.token
        base = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
        configured = board.options.get("country")
        countries = [str(configured)] if configured else [c.lower() for c in self.ctx.countries] or [""]
        cap = int(board.options.get("max_jobs", 400))
        items: list[dict] = []
        for country in countries:
            offset = 0
            country_param = f"country={country}&" if country else ""
            while offset < cap and self.time_left():
                data = self.http.get_json(f"{base}?{country_param}limit={self.PAGE}&offset={offset}")
                data = data if isinstance(data, dict) else {}
                content = data.get("content") or []
                items.extend(item for item in content if isinstance(item, dict))
                total = int(data.get("totalFound", 0) or 0)
                offset += self.PAGE
                if not content or offset >= total:
                    break
        return self.map_parallel(lambda item: self._job(board, base, item), items[:cap])

    def _job(self, board: Board, base: str, item: dict) -> RawJob:
        job_id = str(item.get("id") or "")
        title = normalize_space(item.get("name", ""))
        level = str((item.get("experienceLevel") or {}).get("id", "") or "")
        flags: dict = {"experience_level": level} if level else {}
        keep, reason = self.keep(title, flags)
        detail: dict = {}
        if keep and job_id and self.time_left():
            try:
                fetched = self.http.get_json(f"{base}/{job_id}")
                detail = fetched if isinstance(fetched, dict) else {}
            except FetchError:
                detail = {}
        elif not keep:
            flags["prefilter"] = reason
        location = detail.get("location") or item.get("location") or {}
        location_text = normalize_space(
            location.get("fullLocation")
            or ", ".join(part for part in (location.get("city"), location.get("region"), location.get("country")) if part)
        )
        sections = ((detail.get("jobAd") or {}).get("sections") or {}) if isinstance(detail.get("jobAd"), dict) else {}
        description = "\n".join(
            clean_html(section.get("text", ""))
            for key in ("jobDescription", "qualifications", "additionalInformation")
            if isinstance(section := sections.get(key), dict)
        )
        legacy = f"https://jobs.smartrecruiters.com/{board.token}/{job_id}"
        return RawJob(
            company=board.company or (item.get("company") or {}).get("name", board.token),
            title=title,
            location=location_text,
            url=detail.get("postingUrl") or legacy,
            description=description,
            source=self.name,
            source_id=job_id,
            posted_at=str(item.get("releasedDate", "")),
            posted_date=iso_date(item.get("releasedDate")),
            country_codes=[str(location["country"])] if location.get("country") else [],
            legacy_keys=[legacy_url_key(legacy)],
            flags=flags,
            url_kind="api" if detail.get("postingUrl") else "constructed",
        )
