"""HTML career pages: vetted paginated listings (Cognizant, Deloitte) and a
generic schema.org JobPosting (JSON-LD) extractor for direct job URLs."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..geo import classify_segment, split_segments
from ..http import FetchError
from ..models import Board, RawJob
from ..text import clean_html, normalize_space
from .base import SourceAdapter, iso_date


class PaginatedHtmlAdapter(SourceAdapter):
    name = "paginated_html"

    def list_jobs(self, board: Board) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for page in range(1, int(board.options.get("pages", 3)) + 1):
            if not self.time_left():
                break
            url = paginated_url(board.token, page)
            page_jobs = parse_listing(board, self.http.get_text(url), url)
            if not page_jobs:
                break
            for job in page_jobs:
                key = job.url.split("?")[0].rstrip("/").lower()
                if key not in seen:
                    seen.add(key)
                    jobs.append(job)
        return jobs


class GenericHtmlAdapter(SourceAdapter):
    name = "generic_html"

    def list_jobs(self, board: Board) -> list[RawJob]:
        job = self.fetch_url(board.token)
        return [job] if job else []

    def fetch_url(self, url: str) -> RawJob | None:
        try:
            html = self.http.get_text(url)
        except FetchError:
            return None
        posting = find_job_posting(html)
        if not posting:
            return None
        return job_from_jsonld(posting, url)


def paginated_url(token: str, page: int) -> str:
    if "{page}" in token:
        return token.replace("{page}", str(page))
    if "{offset}" in token:
        return token.replace("{offset}", str((page - 1) * 10))
    parsed = urlparse(token)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if page > 1:
        params["page"] = [str(page)]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(params, doseq=True), parsed.fragment))


def parse_listing(board: Board, html: str, page_url: str) -> list[RawJob]:
    host = urlparse(page_url).netloc.lower()
    if "cognizant.com" in host:
        return _parse_anchor_listing(board, html, page_url, r"/india-en/jobs/[^/]+/[^/]+/?$", india_page="/india-en/" in page_url)
    if "apply.deloitte.com" in host:
        return _parse_anchor_listing(board, html, page_url, r"/careers/JobDetail/", india_page="/SearchJobs/India" in page_url)
    return []


def _parse_anchor_listing(board: Board, html: str, page_url: str, href_pattern: str, india_page: bool) -> list[RawJob]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[RawJob] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        if not re.search(href_pattern, href):
            continue
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not title:
            continue
        container = anchor.find_parent(["article", "li", "div"]) or anchor.parent
        text = normalize_space(container.get_text(" ", strip=True) if container else title)
        location = first_location(text)
        if not location:
            following = anchor.find_next("ul")
            location = first_location(following.get_text(" ", strip=True) if following else "")
        flags: dict[str, Any] = {}
        if not location and india_page:
            flags["geo_hint"] = "india"  # listing page filtered to India but row shows no place
        jobs.append(
            RawJob(
                company=board.company,
                title=title,
                location=location,
                url=urljoin(page_url, href),
                description=clean_html(text),
                source=PaginatedHtmlAdapter.name,
                source_id=_last_numeric_path_part(href),
                flags=flags,
                url_kind="page",
            )
        )
    return jobs


def first_location(text: str) -> str:
    """First India location in a listing row, else the first foreign one, else ''."""
    foreign = ""
    for chunk in re.split(r"\s{2,}| \| |\n|Save Saved|Apply filters", normalize_space(text)):
        for segment in split_segments(chunk):
            status = classify_segment(segment)[0]
            if status == "india":
                return segment.strip(" -|")
            if status == "foreign" and not foreign:
                foreign = segment.strip(" -|")
    return foreign


first_india_location = first_location  # backwards-compatible name


def _last_numeric_path_part(url: str) -> str:
    matches = re.findall(r"/(\d+)(?:/|$)", urlparse(url).path)
    return matches[-1] if matches else ""


# ---------------------------------------------------------------- JSON-LD
def find_job_posting(html: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html or "", "html.parser")
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        found = _walk_jsonld(data)
        if found:
            return found
    return None


def _walk_jsonld(node: Any) -> dict[str, Any] | None:
    if isinstance(node, list):
        for item in node:
            found = _walk_jsonld(item)
            if found:
                return found
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(k).lower() == "jobposting" for k in kinds):
            return node
        if "@graph" in node:
            return _walk_jsonld(node["@graph"])
    return None


def job_from_jsonld(posting: dict[str, Any], url: str) -> RawJob:
    org = posting.get("hiringOrganization")
    company = org.get("name") if isinstance(org, dict) else (org if isinstance(org, str) else "")
    places, codes = [], []
    locations = posting.get("jobLocation")
    for place in locations if isinstance(locations, list) else [locations]:
        if not isinstance(place, dict):
            continue
        address = place.get("address") if isinstance(place.get("address"), dict) else {}
        country = address.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name") or country.get("identifier")
        parts = [address.get("addressLocality"), address.get("addressRegion"), country]
        text = ", ".join(str(p) for p in parts if p)
        if text:
            places.append(normalize_space(text))
        if country:
            codes.append(str(country))
    if str(posting.get("jobLocationType", "")).upper() == "TELECOMMUTE":
        for req in _as_list(posting.get("applicantLocationRequirements")):
            name = req.get("name") if isinstance(req, dict) else req
            if name:
                codes.append(str(name))
    experience = posting.get("experienceRequirements")
    if isinstance(experience, dict) and experience.get("monthsOfExperience"):
        experience = f"{experience['monthsOfExperience']} months of experience"
    description = clean_html(str(posting.get("description", "")))
    if isinstance(experience, str) and experience:
        description = f"{description}\nExperience: {clean_html(experience)}"
    identifier = posting.get("identifier")
    source_id = identifier.get("value") if isinstance(identifier, dict) else (identifier or "")
    return RawJob(
        company=normalize_space(str(company or urlparse(url).netloc)),
        title=normalize_space(str(posting.get("title", ""))),
        location="; ".join(places),
        url=url,
        description=description,
        source=GenericHtmlAdapter.name,
        source_id=str(source_id or ""),
        posted_at=str(posting.get("datePosted", "")),
        posted_date=iso_date(posting.get("datePosted")),
        country_codes=codes,
        url_kind="page",
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([value] if value else [])
