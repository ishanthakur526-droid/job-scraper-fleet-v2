"""LinkedIn public (no-login) job search. OPT-IN ONLY.

Scraping LinkedIn is against its terms of service; this adapter only runs when
the user enables it (``-IncludeLinkedIn`` / ``--include-linkedin``). It never
logs in, keeps to a small request budget, and stops at the first 429/999
(LinkedIn's throttling responses) instead of retrying.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from ..geo import country_name
from ..http import FetchError
from ..models import Board, RawJob
from ..text import clean_html, normalize_space
from .base import SourceAdapter, iso_date

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
INDIA_GEO_ID = "102713980"
# LinkedIn's experience filter per profile level: 1 internship, 2 entry, 3 associate, 4 mid-senior, 5 director, 6 executive.
EXPERIENCE_FILTER = {"student": "1,2", "early_career": "2,3", "mid": "3,4", "senior": "4,5", "leadership": "5,6"}


class LinkedInGuestAdapter(SourceAdapter):
    name = "linkedin_guest"

    def list_jobs(self, board: Board) -> list[RawJob]:
        options = board.options
        queries = list(options.get("queries") or [board.token])
        pages = int(options.get("pages", 2))
        budget = int(options.get("max_requests", 40))
        max_details = int(options.get("max_details", 20))
        window_seconds = int(options.get("posted_within_seconds", 259200))  # 3 days covers weekends
        requests_used = 0
        cards: dict[str, dict] = {}
        places = [country_name(c) for c in self.ctx.countries] or ["Worldwide"]
        for place, query in ((p, q) for p in places for q in queries):
            for page in range(pages):
                if requests_used >= budget or not self.time_left():
                    break
                params = {"keywords": query, "location": place}
                if place == "India":
                    params["geoId"] = INDIA_GEO_ID
                params.update({
                    "f_TPR": f"r{window_seconds}",
                    "f_E": str(options.get("experience_filter") or EXPERIENCE_FILTER.get(self.ctx.level, "2,3")),
                    "start": page * 10,
                })
                html = self._get(f"{SEARCH}?{urlencode(params)}")
                requests_used += 1
                if html is None:
                    return self._finish(cards, 0, budget)
                parsed = parse_search_cards(html)
                for card in parsed:
                    cards.setdefault(card["job_id"], card)
                if len(parsed) < 10:
                    break
        return self._finish(cards, budget - requests_used, max_details)

    def _get(self, url: str) -> str | None:
        try:
            response = self.http.request("GET", url, accept="text/html", raise_for_status=False, retries=0)
        except FetchError as exc:
            self.notes.append(f"stopped: {exc}")
            self.partial = True
            return None
        if response.status in (429, 999) or response.status >= 400:
            self.notes.append(f"stopped at HTTP {response.status} (throttled)")
            self.partial = True
            return None
        return response.text

    def _finish(self, cards: dict[str, dict], requests_left: int, max_details: int) -> list[RawJob]:
        jobs: list[RawJob] = []
        details_left = min(requests_left, max_details)
        for card in cards.values():
            flags: dict = {}
            keep, reason = self.keep(card["title"], flags)
            description = ""
            if keep and details_left > 0 and self.time_left():
                html = self._get(DETAIL.format(job_id=card["job_id"]))
                details_left -= 1
                if html is None:
                    details_left = 0
                else:
                    description, seniority = parse_detail(html)
                    if seniority:
                        flags["experience_level"] = seniority.lower().replace(" ", "_")
            elif not keep:
                flags["prefilter"] = reason
            jobs.append(
                RawJob(
                    company=card["company"] or "Unknown (LinkedIn)",
                    title=card["title"],
                    location=card["location"],
                    url=f"https://www.linkedin.com/jobs/view/{card['job_id']}/",
                    description=description,
                    source=self.name,
                    source_id=card["job_id"],
                    posted_at=card["posted"],
                    posted_date=iso_date(card["posted"]),
                    flags=flags,
                    url_kind="constructed",
                )
            )
        return jobs


def parse_search_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    cards: list[dict] = []
    for card in soup.select("div.base-card, li div.base-search-card"):
        urn = card.get("data-entity-urn") or ""
        match = re.search(r"jobPosting:(\d+)", urn)
        link = card.select_one("a.base-card__full-link")
        if not match and link and link.get("href"):
            match = re.search(r"-(\d{6,})(?:\?|$)", str(link["href"]))
        if not match:
            continue
        title = card.select_one(".base-search-card__title")
        company = card.select_one(".base-search-card__subtitle")
        location = card.select_one(".job-search-card__location")
        posted = card.select_one("time")
        cards.append(
            {
                "job_id": match.group(1),
                "title": normalize_space(title.get_text(" ", strip=True) if title else ""),
                "company": normalize_space(company.get_text(" ", strip=True) if company else ""),
                "location": normalize_space(location.get_text(" ", strip=True) if location else ""),
                "posted": (posted.get("datetime") if posted else "") or "",
            }
        )
    return [card for card in cards if card["title"]]


def parse_detail(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html or "", "html.parser")
    body = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
    description = clean_html(str(body)) if body else ""
    seniority = ""
    for item in soup.select("li.description__job-criteria-item"):
        header = item.select_one("h3")
        value = item.select_one("span")
        if header and value and "seniority" in header.get_text(" ", strip=True).lower():
            seniority = normalize_space(value.get_text(" ", strip=True))
    return description, seniority
