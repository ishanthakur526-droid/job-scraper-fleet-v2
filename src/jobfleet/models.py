from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def legacy_url_key(url: str) -> str:
    """History key used by v2: URL without query string, trailing slash, lowercased.

    The fragment is kept on purpose (TCS links were ``#/jobs/{id}``), so this
    exactly reproduces the keys stored in old ``job_history.csv`` files.
    """
    return (url or "").split("?")[0].rstrip("/").lower()


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    output: str
    target_roles: list = field(default_factory=list)
    positive_keywords: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)
    negative_description_phrases: list[str] = field(default_factory=list)
    excluded_title_patterns: list[str] = field(default_factory=list)
    title_keywords: list[str] = field(default_factory=list)
    route: str = "main"
    domains: list[str] = field(default_factory=list)  # job domains this family owns (e.g. "engineering")


@dataclass(frozen=True)
class Board:
    company: str
    source: str
    token: str
    priority_categories: list[str] = field(default_factory=list)
    enabled: bool = True
    aggregator: bool = False
    options: dict = field(default_factory=dict)
    note: str = ""
    countries: list[str] = field(default_factory=list)  # ISO2 codes a country-specific careers site serves

    @property
    def key(self) -> str:
        return f"{self.source}|{self.token}".lower()


@dataclass
class BoardHealth:
    company: str
    source: str
    token: str
    status: str
    jobs_found: int = 0
    error: str = ""
    retrieved_at: str = field(default_factory=utc_now_iso)
    duration_s: float = 0.0
    hard_failure: bool = False
    board_key: str = ""
    note: str = ""


@dataclass
class RawJob:
    company: str
    title: str
    location: str
    url: str
    description: str
    source: str
    source_id: str = ""
    posted_at: str = ""
    retrieved_at: str = field(default_factory=utc_now_iso)
    board_key: str = ""
    stable_key: str = ""
    legacy_keys: list[str] = field(default_factory=list)
    country_codes: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    requirements_text: str = ""
    preferred_text: str = ""
    flags: dict[str, Any] = field(default_factory=dict)
    url_kind: str = "constructed"
    posted_date: str = ""

    def key(self) -> str:
        if self.stable_key:
            return self.stable_key
        if self.source_id:
            return f"{self.source}:{self.source_id}".lower()
        return legacy_url_key(self.url)

    def all_legacy_keys(self) -> list[str]:
        keys = [legacy_url_key(self.url)] if self.url else []
        keys.extend(key for key in self.legacy_keys if key)
        own = self.key()
        return [key for key in dict.fromkeys(keys) if key and key != own]


@dataclass
class JobResult:
    company: str
    title: str
    experience_required: str
    url: str
    system_notes: str
    category_id: str
    score: int
    source: str
    location: str
    matched_terms: list[str]
    retrieved_at: str
    quality_tier: str = "needs_review"
    is_new: bool = False
    key: str = ""
    route: str = "main"
    posted_date: str = ""
    first_seen: str = ""
    geo_basis: str = ""
    exp_evidence: str = ""
    review_flags: list[str] = field(default_factory=list)
    group_keys: list[str] = field(default_factory=list)
    group_urls: list[str] = field(default_factory=list)
    board_key: str = ""
    legacy_keys: list[str] = field(default_factory=list)
    url_kind: str = "constructed"
    description_snippet: str = ""

    def all_keys(self) -> list[str]:
        return list(dict.fromkeys([self.key, *self.group_keys]))


@dataclass
class RejectedJob:
    company: str
    title: str
    url: str
    source: str
    location: str
    category_id: str
    score: int
    reason: str
    experience_required: str = ""
    matched_terms: list[str] = field(default_factory=list)
    retrieved_at: str = field(default_factory=utc_now_iso)
    stage: str = ""
    key: str = ""
    geo_basis: str = ""
