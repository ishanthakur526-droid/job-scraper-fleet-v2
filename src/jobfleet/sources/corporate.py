"""Single-company career APIs: Accenture, Capgemini, TCS iBegin."""

from __future__ import annotations

from urllib.parse import urlencode

from ..http import FetchError
from ..models import Board, RawJob, legacy_url_key
from ..text import clean_html, normalize_space
from .base import SourceAdapter, iso_date


class AccentureAdapter(SourceAdapter):
    name = "accenture"
    ENDPOINT = "https://www.accenture.com/api/accenture/elastic/findjobs"

    def list_jobs(self, board: Board) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen: set[str] = set()
        pages = int(board.options.get("pages", 4))
        for start in range(0, pages * 12, 12):
            if not self.time_left():
                break
            data = self.http.post_form(
                self.ENDPOINT,
                {
                    "startIndex": str(start),
                    "maxResultSize": "12",
                    "jobKeyword": board.token,
                    "jobCountry": "India",
                    "jobLanguage": "en",
                    "countrySite": "in-en",
                    "sortBy": "1",
                    "searchType": "vectorSearch",
                    "enableQueryBoost": "true",
                    "minScore": "0.6",
                    "getFeedbackJudgmentEnabled": "true",
                    "useCleanEmbedding": "true",
                    "score": "true",
                    "totalHits": "true",
                    "debugQuery": "false",
                    "jobFilters": "[]",
                },
                headers={"Origin": "https://www.accenture.com", "Referer": "https://www.accenture.com/in-en/careers/jobsearch"},
            )
            page = data.get("data", []) if isinstance(data, dict) else []
            if not page:
                break
            for item in page:
                job_id = str(item.get("requisitionId") or item.get("guid") or "")
                if job_id and job_id not in seen:
                    seen.add(job_id)
                    jobs.append(self._job(board, item, job_id))
        return jobs

    def _job(self, board: Board, item: dict, job_id: str) -> RawJob:
        location = _join(item.get("location")) or normalize_space(str(item.get("feedCity", "")))
        detail_url = str(item.get("jobDetailUrl", "")).replace("{0}", "in-en") or (
            f"https://www.accenture.com/in-en/careers/jobdetails?id={job_id}"
        )
        years = normalize_space(str(item.get("yearsOfExperience", "") or ""))
        description = "\n".join(
            part
            for part in (
                str(item.get("jobDescriptionClean", "")),
                clean_html(str(item.get("jobDescription", ""))),
                str(item.get("qualificationClean", "")),
                _join(item.get("mustHaveSkills")),
                _join(item.get("goodToHaveSkills")),
                f"Experience: {years}" if years and "year" in years.lower() else (f"Experience: {years} years" if years else ""),
            )
            if part
        )
        posted = item.get("updateDate") or item.get("postedDateText") or ""
        return RawJob(
            company=board.company,
            title=normalize_space(str(item.get("title", ""))),
            location=normalize_space(location),
            url=detail_url,
            description=clean_html(description),
            source=self.name,
            source_id=job_id,
            posted_at=str(posted),
            posted_date=iso_date(posted),
            country_codes=["IN"] if str(item.get("country", "")).lower() == "india" else [],
            url_kind="api" if item.get("jobDetailUrl") else "constructed",
        )


class CapgeminiAdapter(SourceAdapter):
    name = "capgemini"

    def list_jobs(self, board: Board) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for page_number in range(1, int(board.options.get("pages", 2)) + 1):
            if not self.time_left():
                break
            query = urlencode({"page": str(page_number), "size": "50", "country_code": "in-en", "search": board.token})
            data = self.http.get_json(f"https://cg-jobstream-api.azurewebsites.net/api/job-search?{query}")
            page = data.get("data", []) if isinstance(data, dict) else []
            if not page:
                break
            for item in page:
                job_id = str(item.get("id") or item.get("_id") or item.get("ref") or "")
                url = item.get("apply_job_url") or item.get("wp_url") or ""
                if not job_id or job_id in seen:
                    continue
                if not url:  # v2 fell back to a generic search page: useless link, colliding history keys
                    continue
                seen.add(job_id)
                jobs.append(
                    RawJob(
                        company=board.company,
                        title=normalize_space(item.get("title", "")),
                        location=normalize_space(item.get("location", "")),
                        url=url,
                        description=clean_html(item.get("description", "") or item.get("description_stripped", "")),
                        source=self.name,
                        source_id=job_id,
                        posted_at=str(item.get("updated_at", "")),
                        posted_date=iso_date(item.get("updated_at")),
                        url_kind="api",
                    )
                )
        return jobs


class TcsIbeginAdapter(SourceAdapter):
    """TCS iBegin (rebuilt in 2026 as a single-page app at /candidate/next).

    The public search API needs the XSRF token the site issues to every visitor
    as a cookie (a CSRF guard, no login). Results carry structured experience
    bands, so no per-job detail calls are needed. Job pages: /en-IN/jobs/{id}.
    """

    name = "tcs_ibegin"
    BASE = "https://ibegin.tcsapps.com/candidate/next"
    PAGE_SIZE = 50

    def list_jobs(self, board: Board) -> list[RawJob]:
        # Same bootstrap the site's front-end does on load: the anonymous /api/candidate call
        # answers 403 but issues the SESSION and XSRF-TOKEN cookies used by the search API.
        self.http.get_text(f"{self.BASE}/")
        self.http.request("GET", f"{self.BASE}/api/candidate", accept="application/json", raise_for_status=False, retries=0)
        token = self.http.cookies("ibegin.tcsapps.com").get("XSRF-TOKEN", "")
        if not token:
            raise FetchError("TCS iBegin did not issue an XSRF token (site changed?)")
        headers = {"next-xsrf-token": token, "Origin": "https://ibegin.tcsapps.com", "Referer": f"{self.BASE}/en-IN/landing"}
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for page_number in range(1, int(board.options.get("pages", 3)) + 1):
            if not self.time_left():
                break
            body = {
                "includeRegularJob": True, "includeWalkIn": True, "searchTerms": [board.token] if board.token else [],
                "jobLocationFilters": [], "jobDomainFilters": [], "experienceLevelFilters": [], "skillFilters": [],
                "relevancySortOrder": "desc", "recentSortOrder": None, "lastDateToApplySortOrder": None,
                "page": page_number, "resultsPerPage": self.PAGE_SIZE,
            }
            data = self.http.post_json(f"{self.BASE}/api/en-IN/search/jobs", body, headers=headers)
            payload = (data.get("payload") or {}) if isinstance(data, dict) else {}
            content = [item for item in payload.get("content") or [] if isinstance(item, dict)]
            for item in content:
                job_id = str(item.get("id", ""))
                if job_id and job_id not in seen:
                    seen.add(job_id)
                    jobs.append(self._job(board, item, job_id))
            if not content or payload.get("last"):
                break
        return jobs

    def _job(self, board: Board, item: dict, job_id: str) -> RawJob:
        low, high = item.get("minimumExperienceInYears"), item.get("maximumExperienceInYears")
        lines = [
            f"Domain: {item.get('domain', '')}",
            f"Skills: {_join(item.get('skills'))}",
            f"Experience: {low} - {high} years" if low is not None and high is not None else "",
            "Walk-in drive" if item.get("walkIn") else "",
        ]
        return RawJob(
            company=board.company,
            title=normalize_space(item.get("title", "")),
            location=normalize_space(item.get("location", "")),
            url=f"{self.BASE}/en-IN/jobs/{job_id}",
            description="\n".join(line for line in lines if line),
            source=self.name,
            source_id=job_id,
            posted_at=str(item.get("applyBy", "")),
            legacy_keys=[legacy_url_key(f"https://ibegin.tcsapps.com/candidate/#/jobs/{job_id}")],
            url_kind="constructed",
        )


def _join(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(normalize_space(str(part)) for part in value if part)
    return normalize_space(str(value or ""))
