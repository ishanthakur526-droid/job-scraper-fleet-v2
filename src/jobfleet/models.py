from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    output: str
    target_roles: list[str]
    positive_keywords: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Board:
    company: str
    source: str
    token: str
    priority_categories: list[str] = field(default_factory=list)


@dataclass
class BoardHealth:
    company: str
    source: str
    token: str
    status: str
    jobs_found: int = 0
    error: str = ""
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
