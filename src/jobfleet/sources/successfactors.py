"""SuccessFactors-style career sites (listing table + detail pages), e.g. careers.ey.com."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..geo import classify_segment
from ..http import FetchError
from ..models import Board, RawJob
from ..text import clean_html, normalize_space
from .base import SourceAdapter, iso_date


class SuccessFactorsAdapter(SourceAdapter):
    name = "successfactors"
    PAGE_SIZE = 25

    def list_jobs(self, board: Board) -> list[RawJob]:
        max_jobs = int(board.options.get("max_jobs", 75))
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for offset in range(0, max_jobs, self.PAGE_SIZE):
            if not self.time_left():
                break
            page_url = page_url_for(board.token, offset)
            links = extract_listing_links(self.http.get_text(page_url), page_url)
            new_links = 0
            for title, url, list_location in links:
                key = url.split("?")[0].rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)
                new_links += 1
                jobs.append(self._job(board, title, url, list_location))
                if len(jobs) >= max_jobs:
                    break
            if not links or not new_links or len(jobs) >= max_jobs:
                break
        return jobs

    def _job(self, board: Board, title: str, url: str, list_location: str) -> RawJob:
        flags: dict = {}
        keep, reason = self.keep(title, flags)
        detail_html = ""
        if keep and self.time_left():
            try:
                detail_html = self.http.get_text(url)
            except FetchError:
                detail_html = ""
        elif not keep:
            flags["prefilter"] = reason
        description = clean_html(detail_html)
        location = detail_location(description) or list_location
        return RawJob(
            company=board.company,
            title=normalize_space(detail_title(detail_html) or title),
            location=normalize_space(location),
            url=url,
            description=description,
            source=self.name,
            source_id=source_id_from_url(url),
            posted_at=posted_text(description),
            posted_date=iso_date(posted_text(description)),
            flags=flags,
            url_kind="page",
        )


def page_url_for(token: str, offset: int) -> str:
    parsed = urlparse(token)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if offset:
        params["startrow"] = [str(offset)]
    else:
        params.pop("startrow", None)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(params, doseq=True), parsed.fragment))


def extract_listing_links(html: str, page_url: str) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    links: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        if "/job/" not in href:
            continue
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not title or title.lower() in {"title", "job title"}:
            continue
        url = urljoin(page_url, href)
        key = url.split("?")[0].rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        links.append((title, url, _listing_location(anchor)))
    return links


def _listing_location(anchor) -> str:
    row = anchor.find_parent("tr")
    if not row:
        return ""
    title = normalize_space(anchor.get_text(" ", strip=True)).lower()
    cells = [normalize_space(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
    candidates = [cell for cell in cells if cell and cell.lower() != title]
    for cell in candidates:
        if classify_segment(cell)[0] == "india":
            return cell
    return candidates[0] if candidates else ""


def detail_title(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for selector in ("h1", ".jobTitle", "[data-automation-id='jobPostingHeader']", "h2"):
        element = soup.select_one(selector)
        if element:
            title = normalize_space(element.get_text(" ", strip=True))
            if title:
                return title
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    return clean_html(match.group(1)).split("|")[0].strip() if match else ""


def detail_location(text: str) -> str:
    for pattern in (
        r"\bLocation:\s*(.*?)(?:\bOther locations:|\bDate:|\bRequisition ID:|\bJob Segment:|\n|$)",
        r"\bPrimary Location:\s*(.*?)(?:\bOther locations:|\bDate:|\bRequisition ID:|\bJob Segment:|\n|$)",
    ):
        match = re.search(pattern, text or "", flags=re.I)
        if match and normalize_space(match.group(1)):
            return normalize_space(match.group(1))
    return ""


def posted_text(text: str) -> str:
    match = re.search(r"\bDate:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", text or "")
    return match.group(1) if match else ""


def source_id_from_url(url: str) -> str:
    match = re.search(r"/(\d+)/?$", urlparse(url).path)
    return match.group(1) if match else ""
