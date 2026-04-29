from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from ..http import FetchError, HttpClient
from ..models import Board, RawJob
from ..text import clean_html, is_india_job, normalize_space


class SourceAdapter(ABC):
    name: str

    def __init__(self, http: HttpClient):
        self.http = http

    @abstractmethod
    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        raise NotImplementedError

    def fetch_url(self, url: str) -> RawJob | None:
        return None


class LeverAdapter(SourceAdapter):
    name = "lever"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        url = f"https://api.lever.co/v0/postings/{board.token}?mode=json"
        data = self.http.get_json(url)
        if not isinstance(data, list):
            return []
        jobs: list[RawJob] = []
        for item in data:
            categories = item.get("categories") or {}
            location = categories.get("location") or ", ".join(categories.get("allLocations") or [])
            description = item.get("descriptionPlain") or item.get("description") or ""
            lists = " ".join(part.get("text", "") for part in item.get("lists", []) if isinstance(part, dict))
            jobs.append(
                RawJob(
                    company=board.company,
                    title=normalize_space(item.get("text", "")),
                    location=normalize_space(location),
                    url=item.get("hostedUrl") or item.get("applyUrl") or f"https://jobs.lever.co/{board.token}/{item.get('id', '')}",
                    description=clean_html(f"{description} {lists}"),
                    source=self.name,
                    source_id=item.get("id", ""),
                    posted_at=str(item.get("createdAt", "")),
                )
            )
        return jobs


class GreenhouseAdapter(SourceAdapter):
    name = "greenhouse"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board.token}/jobs?content=true"
        data = self.http.get_json(url)
        jobs: list[RawJob] = []
        for item in data.get("jobs", []):
            location = (item.get("location") or {}).get("name", "")
            jobs.append(
                RawJob(
                    company=board.company,
                    title=normalize_space(item.get("title", "")),
                    location=normalize_space(location),
                    url=item.get("absolute_url") or f"https://boards.greenhouse.io/{board.token}/jobs/{item.get('id', '')}",
                    description=clean_html(item.get("content", "")),
                    source=self.name,
                    source_id=str(item.get("id", "")),
                    posted_at=item.get("updated_at", ""),
                )
            )
        return jobs


class AshbyAdapter(SourceAdapter):
    name = "ashby"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{board.token}?includeCompensation=false"
        data = self.http.get_json(url)
        jobs: list[RawJob] = []
        for item in data.get("jobs", []):
            description = item.get("descriptionPlain") or item.get("descriptionHtml") or ""
            jobs.append(
                RawJob(
                    company=board.company,
                    title=normalize_space(item.get("title", "")),
                    location=normalize_space(item.get("location", "")),
                    url=item.get("jobUrl") or item.get("applicationUrl") or f"https://jobs.ashbyhq.com/{board.token}/{item.get('id', '')}",
                    description=clean_html(description),
                    source=self.name,
                    source_id=item.get("id", ""),
                    posted_at=item.get("publishedAt", ""),
                )
            )
        return jobs


class SmartRecruitersAdapter(SourceAdapter):
    name = "smartrecruiters"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        token = board.token
        jobs: list[RawJob] = []
        offset = 0
        limit = 100
        total = 1
        while offset < total and offset < 100:
            url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit={limit}&offset={offset}"
            data = self.http.get_json(url)
            total = int(data.get("totalFound", 0) or 0)
            content = data.get("content", [])
            if not content:
                break
            for item in content:
                detail = self._detail(token, item)
                jobs.append(self._raw_job(board, token, item, detail))
            offset += limit
        return jobs

    def _detail(self, token: str, item: dict) -> dict:
        job_id = item.get("id")
        if not job_id:
            return item
        try:
            detail = self.http.get_json(f"https://api.smartrecruiters.com/v1/companies/{token}/postings/{job_id}")
            return detail if isinstance(detail, dict) else item
        except FetchError:
            return item

    def _raw_job(self, board: Board, token: str, item: dict, detail: dict) -> RawJob:
        location = detail.get("location") or item.get("location") or {}
        location_text = ", ".join(
            part for part in [
                location.get("city", ""),
                location.get("region", ""),
                location.get("country", ""),
            ]
            if part
        )
        sections = detail.get("jobAd", {}).get("sections", {}) if isinstance(detail.get("jobAd"), dict) else {}
        description_parts = [
            detail.get("name", ""),
            sections.get("jobDescription", {}).get("text", "") if isinstance(sections.get("jobDescription"), dict) else "",
            sections.get("qualifications", {}).get("text", "") if isinstance(sections.get("qualifications"), dict) else "",
            sections.get("additionalInformation", {}).get("text", "") if isinstance(sections.get("additionalInformation"), dict) else "",
        ]
        job_id = item.get("id") or detail.get("id") or ""
        return RawJob(
            company=board.company or (detail.get("company") or {}).get("name", token),
            title=normalize_space(detail.get("name") or item.get("name", "")),
            location=normalize_space(location_text),
            url=f"https://jobs.smartrecruiters.com/{token}/{job_id}",
            description=clean_html(" ".join(description_parts)),
            source=self.name,
            source_id=str(job_id),
            posted_at=detail.get("releasedDate", "") or item.get("releasedDate", ""),
        )


class AmazonJobsAdapter(SourceAdapter):
    name = "amazon_jobs"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        jobs: list[RawJob] = []
        seen = set()
        for offset in range(0, 50, 10):
            query = urlencode(
                {
                    "base_query": board.token,
                    "country": "IND",
                    "offset": str(offset),
                    "result_limit": "10",
                }
            )
            data = self.http.get_json(f"https://www.amazon.jobs/en/search.json?{query}")
            page_jobs = data.get("jobs", []) if isinstance(data, dict) else []
            if not page_jobs:
                break
            for item in page_jobs:
                job_id = str(item.get("id", ""))
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                description = " ".join(
                    str(part or "")
                    for part in [
                        item.get("description", ""),
                        item.get("basic_qualifications", ""),
                        item.get("preferred_qualifications", ""),
                    ]
                )
                location = item.get("normalized_location") or ", ".join(
                    part for part in [item.get("city", ""), item.get("country_code", "")] if part
                )
                jobs.append(
                    RawJob(
                        company=board.company,
                        title=normalize_space(item.get("title", "")),
                        location=normalize_space(location),
                        url=f"https://www.amazon.jobs/en/jobs/{job_id}",
                        description=clean_html(description),
                        source=self.name,
                        source_id=job_id,
                        posted_at=str(item.get("posted_date", "")),
                    )
                )
        return jobs


class AccentureAdapter(SourceAdapter):
    name = "accenture"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        jobs: list[RawJob] = []
        seen = set()
        for start in range(0, 48, 12):
            data = self.http.post_form(
                "https://www.accenture.com/api/accenture/elastic/findjobs",
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
                headers={
                    "Origin": "https://www.accenture.com",
                    "Referer": "https://www.accenture.com/in-en/careers/jobsearch",
                },
            )
            page_jobs = data.get("data", []) if isinstance(data, dict) else []
            if not page_jobs:
                break
            for item in page_jobs:
                job_id = str(item.get("requisitionId") or item.get("guid") or "")
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                jobs.append(self._raw_job(board, item, job_id))
        return jobs

    def _raw_job(self, board: Board, item: dict, job_id: str) -> RawJob:
        location = self._join(item.get("location")) or normalize_space(str(item.get("feedCity", ""))) or "India"
        detail_url = str(item.get("jobDetailUrl", ""))
        if detail_url:
            detail_url = detail_url.replace("{0}", "in-en")
        else:
            detail_url = f"https://www.accenture.com/in-en/careers/jobdetails?id={job_id}"
        description = " ".join(
            part
            for part in [
                str(item.get("jobDescriptionClean", "")),
                clean_html(str(item.get("jobDescription", ""))),
                str(item.get("qualificationClean", "")),
                self._join(item.get("mustHaveSkills")),
                self._join(item.get("goodToHaveSkills")),
                self._join(item.get("workdaySkill")),
                str(item.get("yearsOfExperience", "")),
            ]
            if part
        )
        return RawJob(
            company=board.company,
            title=normalize_space(str(item.get("title", ""))),
            location=normalize_space(location),
            url=detail_url,
            description=clean_html(description),
            source=self.name,
            source_id=job_id,
            posted_at=str(item.get("updateDate", "") or item.get("postedDateText", "")),
        )

    def _join(self, value: object) -> str:
        if isinstance(value, list):
            return ", ".join(normalize_space(str(part)) for part in value if part)
        return normalize_space(str(value or ""))


class CapgeminiAdapter(SourceAdapter):
    name = "capgemini"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        jobs: list[RawJob] = []
        seen = set()
        for page in range(1, 3):
            query = urlencode(
                {
                    "page": str(page),
                    "size": "50",
                    "country_code": "in-en",
                    "search": board.token,
                }
            )
            data = self.http.get_json(f"https://cg-jobstream-api.azurewebsites.net/api/job-search?{query}")
            page_jobs = data.get("data", []) if isinstance(data, dict) else []
            if not page_jobs:
                break
            for item in page_jobs:
                job_id = str(item.get("id") or item.get("_id") or item.get("ref") or "")
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                jobs.append(
                    RawJob(
                        company=board.company,
                        title=normalize_space(item.get("title", "")),
                        location=normalize_space(item.get("location", "") or "India"),
                        url=item.get("apply_job_url") or item.get("wp_url") or "https://www.capgemini.com/in-en/careers/join-capgemini/job-search/",
                        description=clean_html(item.get("description", "") or item.get("description_stripped", "")),
                        source=self.name,
                        source_id=job_id,
                        posted_at=str(item.get("updated_at", "")),
                    )
                )
        return jobs


class TcsIbeginAdapter(SourceAdapter):
    name = "tcs_ibegin"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        jobs: list[RawJob] = []
        seen = set()
        for page in range(1, 6):
            payload = {
                "jobTitle": None,
                "jobCity": None,
                "jobFunction": None,
                "jobExperience": None,
                "jobSkill": None,
                "pageNumber": str(page),
                "userText": board.token,
                "jobTitleOrder": None,
                "jobCityOrder": None,
                "jobFunctionOrder": None,
                "jobExperienceOrder": None,
                "applyByOrder": None,
                "regular": True,
                "walkin": True,
            }
            data = self.http.post_json(
                "https://ibegin.tcsapps.com/candidate/api/v1/jobs/searchJ",
                payload,
                headers={
                    "Origin": "https://ibegin.tcsapps.com",
                    "Referer": "https://ibegin.tcsapps.com/candidate/jobs/search",
                },
            )
            page_jobs = data.get("data", {}).get("jobs", []) if isinstance(data, dict) else []
            if not page_jobs:
                break
            for item in page_jobs:
                job_id = str(item.get("id", ""))
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                skills = item.get("skills") or ""
                experience = item.get("experience") or ""
                description = f"{item.get('functionName', '')} {skills} Experience: {experience} years"
                jobs.append(
                    RawJob(
                        company=board.company,
                        title=normalize_space(item.get("jobTitle", "")),
                        location=normalize_space(item.get("location", "")),
                        url=f"https://ibegin.tcsapps.com/candidate/#/jobs/{job_id}",
                        description=clean_html(description),
                        source=self.name,
                        source_id=job_id,
                        posted_at=str(item.get("applyByDate", "")),
                    )
                )
        return jobs


class WorkdayAdapter(SourceAdapter):
    name = "workday"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        host, tenant, site = _parse_workday_token(board.token)
        endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/en-US/{site}",
        }
        jobs: list[RawJob] = []
        seen = set()
        max_jobs = 100
        for search_text in ("India", ""):
            offset = 0
            payload = {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": search_text}
            data = self.http.post_json(endpoint, payload, headers=headers)
            total = int(data.get("total", 0) or 0)
            while offset < total and len(jobs) < max_jobs:
                if offset:
                    payload["offset"] = offset
                    data = self.http.post_json(endpoint, payload, headers=headers)
                postings = data.get("jobPostings", [])
                if not postings:
                    break
                for item in postings:
                    if len(jobs) >= max_jobs:
                        break
                    key = item.get("externalPath") or item.get("title")
                    if key in seen:
                        continue
                    seen.add(key)
                    jobs.append(self._raw_job(board, host, tenant, site, item))
                offset += int(payload["limit"])
            if len(jobs) >= max_jobs:
                break
        return jobs

    def _raw_job(self, board: Board, host: str, tenant: str, site: str, item: dict) -> RawJob:
        external_path = item.get("externalPath", "")
        detail = {}
        list_location = item.get("locationsText", "")
        if not list_location and isinstance(item.get("bulletFields"), list):
            list_location = ", ".join(str(part) for part in item.get("bulletFields", []))
        if external_path and is_india_job(list_location, item.get("title", "")):
            try:
                detail_url = f"https://{host}/wday/cxs/{tenant}/{site}{external_path}"
                detail_obj = self.http.get_json(detail_url)
                detail = detail_obj if isinstance(detail_obj, dict) else {}
            except FetchError:
                detail = {}
        info = detail.get("jobPostingInfo", {}) if isinstance(detail.get("jobPostingInfo"), dict) else {}
        description = info.get("jobDescription", "")
        location = info.get("location", "") or list_location
        title = info.get("title", "") or item.get("title", "")
        apply_url = f"https://{host}/en-US/{site}{external_path}" if external_path else f"https://{host}/en-US/{site}"
        return RawJob(
            company=board.company,
            title=normalize_space(title),
            location=normalize_space(location),
            url=apply_url,
            description=clean_html(description),
            source=self.name,
            source_id="; ".join(item.get("bulletFields", [])) if isinstance(item.get("bulletFields"), list) else "",
            posted_at=item.get("postedOn", ""),
        )


class SuccessFactorsAdapter(SourceAdapter):
    name = "successfactors"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        jobs: list[RawJob] = []
        seen = set()
        max_jobs = 50
        detail_limit = 20
        for offset in range(0, max_jobs, 25):
            page_url = _successfactors_page_url(board.token, offset)
            html = self.http.get_text(page_url)
            links = self._extract_listing_links(html, page_url)
            if not links:
                break
            new_links = 0
            for title, url, list_location in links:
                key = url.split("?")[0].rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)
                new_links += 1
                fetch_detail = len(jobs) < detail_limit
                jobs.append(self._raw_job(board, title, url, list_location, fetch_detail))
                if len(jobs) >= max_jobs:
                    break
            if len(jobs) >= max_jobs or not new_links:
                break
        return jobs

    def _extract_listing_links(self, html: str, page_url: str) -> list[tuple[str, str, str]]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        links: list[tuple[str, str, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", ""))
            if "/job/" not in href:
                continue
            title = normalize_space(anchor.get_text(" ", strip=True))
            if not title or title.lower() in {"title", "job title"}:
                continue
            url = urljoin(page_url, href)
            location = _successfactors_listing_location(anchor)
            links.append((title, url, location))
        return _dedupe_listing_links(links)

    def _raw_job(self, board: Board, title: str, url: str, list_location: str, fetch_detail: bool) -> RawJob:
        detail_html = ""
        if fetch_detail:
            try:
                detail_html = self.http.get_text(url)
            except FetchError:
                detail_html = ""

        description = clean_html(detail_html)
        detail_title = _successfactors_detail_title(detail_html) or title
        location = _successfactors_detail_location(description) or list_location
        return RawJob(
            company=board.company,
            title=normalize_space(detail_title),
            location=normalize_space(location),
            url=url,
            description=description,
            source=self.name,
            source_id=_successfactors_source_id(url),
            posted_at=_successfactors_posted_at(description),
        )


class PaginatedHtmlAdapter(SourceAdapter):
    name = "paginated_html"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        jobs: list[RawJob] = []
        seen = set()
        for page in range(1, 4):
            url = _paginated_html_url(board.token, page)
            html = self.http.get_text(url)
            page_jobs = _parse_paginated_html_jobs(board, html, url)
            if not page_jobs:
                break
            for job in page_jobs:
                key = job.url.split("?")[0].rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)
                jobs.append(job)
        return jobs


class GenericHtmlAdapter(SourceAdapter):
    name = "generic_html"

    def list_jobs(self, board: Board) -> Iterable[RawJob]:
        return []

    def fetch_url(self, url: str) -> RawJob | None:
        try:
            html = self.http.get_text(url)
        except FetchError:
            return None
        title = _first_jsonld_value(html, "title") or _html_title(html)
        company = _first_jsonld_value(html, "hiringOrganization.name") or _hostname_company(url)
        location = _first_jsonld_value(html, "jobLocation.address.addressCountry") or _first_jsonld_value(html, "jobLocation.address.addressLocality")
        description = _first_jsonld_value(html, "description") or html
        return RawJob(
            company=company,
            title=normalize_space(title),
            location=normalize_space(location),
            url=url,
            description=clean_html(description),
            source=self.name,
        )


def adapter_for(source: str, http: HttpClient) -> SourceAdapter:
    adapters: dict[str, type[SourceAdapter]] = {
        LeverAdapter.name: LeverAdapter,
        GreenhouseAdapter.name: GreenhouseAdapter,
        AshbyAdapter.name: AshbyAdapter,
        SmartRecruitersAdapter.name: SmartRecruitersAdapter,
        AmazonJobsAdapter.name: AmazonJobsAdapter,
        AccentureAdapter.name: AccentureAdapter,
        CapgeminiAdapter.name: CapgeminiAdapter,
        TcsIbeginAdapter.name: TcsIbeginAdapter,
        WorkdayAdapter.name: WorkdayAdapter,
        SuccessFactorsAdapter.name: SuccessFactorsAdapter,
        PaginatedHtmlAdapter.name: PaginatedHtmlAdapter,
        GenericHtmlAdapter.name: GenericHtmlAdapter,
    }
    return adapters[source](http)


def board_from_url(url: str) -> Board | None:
    patterns = [
        (r"jobs(?:\.eu)?\.lever\.co/([^/?#]+)/?", "lever"),
        (r"boards\.greenhouse\.io/([^/?#]+)/?", "greenhouse"),
        (r"job-boards\.eu\.greenhouse\.io/([^/?#]+)/?", "greenhouse"),
        (r"jobs\.ashbyhq\.com/([^/?#]+)/?", "ashby"),
        (r"careers\.smartrecruiters\.com/([^/?#]+)/?", "smartrecruiters"),
        (r"jobs\.smartrecruiters\.com/([^/?#]+)/?", "smartrecruiters"),
    ]
    for pattern, source in patterns:
        match = re.search(pattern, url)
        if match:
            token = match.group(1)
            return Board(company=token, source=source, token=token)
    workday = _board_from_workday_url(url)
    if workday:
        return workday
    successfactors = _board_from_successfactors_url(url)
    if successfactors:
        return successfactors
    return None


def _board_from_workday_url(url: str) -> Board | None:
    match = re.search(r"https?://([^/]*myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}|en-US)/([^/?#]+)", url)
    if not match:
        return None
    host, site = match.group(1), match.group(2)
    tenant = host.split(".")[0]
    token = f"{host}|{tenant}|{site}"
    return Board(company=tenant, source=WorkdayAdapter.name, token=token)


def _parse_workday_token(token: str) -> tuple[str, str, str]:
    parts = token.split("|")
    if len(parts) != 3:
        raise ValueError("Workday token must be host|tenant|site")
    return parts[0], parts[1], parts[2]


def _board_from_successfactors_url(url: str) -> Board | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() == "careers.ey.com" and parsed.path.startswith("/ey/"):
        token = "https://careers.ey.com/ey/search/?q=&locationsearch=India"
        return Board(company="EY", source=SuccessFactorsAdapter.name, token=token)
    if parsed.netloc.lower() == "careers.ltimindtree.com":
        token = "https://careers.ltimindtree.com/search/?q=&optionsFacetsDD_country=IN"
        return Board(company="LTIMindtree", source=SuccessFactorsAdapter.name, token=token)
    return None


def _successfactors_page_url(token: str, offset: int) -> str:
    parsed = urlparse(token)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if offset:
        params["startrow"] = [str(offset)]
    else:
        params.pop("startrow", None)
    query = urlencode(params, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def _successfactors_listing_location(anchor) -> str:
    row = anchor.find_parent("tr")
    if not row:
        return ""
    cells = [normalize_space(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
    title = normalize_space(anchor.get_text(" ", strip=True))
    candidates = [cell for cell in cells if cell and cell.lower() != title.lower()]
    if not candidates:
        return ""
    for cell in candidates:
        if is_india_job(cell):
            return cell
    return candidates[0]


def _successfactors_detail_title(html: str) -> str:
    if not html:
        return ""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for selector in ("h1", "h2", ".jobTitle", "[data-automation-id='jobPostingHeader']"):
        element = soup.select_one(selector)
        if element:
            title = normalize_space(element.get_text(" ", strip=True))
            if title:
                return title
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if match:
        return clean_html(match.group(1)).split("|")[0].strip()
    return ""


def _successfactors_detail_location(text: str) -> str:
    patterns = [
        r"\bLocation:\s*(.*?)(?:\bOther locations:|\bDate:|\bRequisition ID:|\bJob Segment:|$)",
        r"\bPrimary Location:\s*(.*?)(?:\bOther locations:|\bDate:|\bRequisition ID:|\bJob Segment:|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.S)
        if match:
            return normalize_space(match.group(1))
    return ""


def _successfactors_posted_at(text: str) -> str:
    match = re.search(r"\bDate:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", text)
    return match.group(1) if match else ""


def _successfactors_source_id(url: str) -> str:
    match = re.search(r"/(\d+)/?$", urlparse(url).path)
    return match.group(1) if match else ""


def _dedupe_listing_links(links: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen = set()
    output: list[tuple[str, str, str]] = []
    for title, url, location in links:
        key = url.split("?")[0].rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        output.append((title, url, location))
    return output


def _paginated_html_url(token: str, page: int) -> str:
    if "{page}" in token:
        return token.replace("{page}", str(page))
    if "{offset}" in token:
        return token.replace("{offset}", str((page - 1) * 10))
    parsed = urlparse(token)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if page > 1:
        params["page"] = [str(page)]
    query = urlencode(params, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def _parse_paginated_html_jobs(board: Board, html: str, page_url: str) -> list[RawJob]:
    parsed = urlparse(page_url)
    host = parsed.netloc.lower()
    if "cognizant.com" in host:
        return _parse_cognizant_jobs(board, html, page_url)
    if "apply.deloitte.com" in host:
        return _parse_deloitte_jobs(board, html, page_url)
    return []


def _parse_cognizant_jobs(board: Board, html: str, page_url: str) -> list[RawJob]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    jobs: list[RawJob] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        if not re.search(r"/india-en/jobs/[^/]+/[^/]+/?$", href):
            continue
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not title:
            continue
        container = anchor.find_parent(["article", "li", "div"]) or anchor.parent
        text = normalize_space(container.get_text(" ", strip=True) if container else title)
        location = _first_india_location(text)
        if not location:
            next_list = anchor.find_next("ul")
            location = _first_india_location(next_list.get_text(" ", strip=True) if next_list else "")
        jobs.append(
            RawJob(
                company=board.company,
                title=title,
                location=normalize_space(location),
                url=urljoin(page_url, href),
                description=clean_html(text),
                source=PaginatedHtmlAdapter.name,
                source_id=_last_numeric_path_part(href),
            )
        )
    return jobs


def _parse_deloitte_jobs(board: Board, html: str, page_url: str) -> list[RawJob]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    jobs: list[RawJob] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        if "/careers/JobDetail/" not in href:
            continue
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not title:
            continue
        container = anchor.find_parent(["article", "li", "div"]) or anchor.parent
        text = normalize_space(container.get_text(" ", strip=True) if container else title)
        location = _first_india_location(text) or ("India" if "/SearchJobs/India" in page_url else "")
        jobs.append(
            RawJob(
                company=board.company,
                title=title,
                location=normalize_space(location),
                url=urljoin(page_url, href),
                description=clean_html(f"{text} India"),
                source=PaginatedHtmlAdapter.name,
                source_id=_last_numeric_path_part(href),
            )
        )
    return jobs


def _first_india_location(text: str) -> str:
    normalized = normalize_space(text)
    if not normalized:
        return ""
    chunks = re.split(r"\s{2,}| \| |\n|Save Saved|Apply filters", normalized)
    for chunk in chunks:
        if is_india_job(chunk):
            return chunk.strip(" -|")
    if is_india_job(normalized):
        return normalized
    return ""


def _last_numeric_path_part(url: str) -> str:
    matches = re.findall(r"/(\d+)(?:/|$)", urlparse(url).path)
    return matches[-1] if matches else ""


def _html_title(value: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", value, flags=re.I | re.S)
    return clean_html(match.group(1)) if match else ""


def _hostname_company(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else "Unknown"


def _first_jsonld_value(_html: str, _path: str) -> str:
    # Placeholder for generic pages. Structured ATS APIs are preferred, and this
    # keeps generic extraction conservative instead of pretending weak data is exact.
    return ""
