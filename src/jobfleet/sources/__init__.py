"""Source adapter registry and career-URL recognition."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from ..http import HttpClient
from ..models import Board
from .amazon import AmazonJobsAdapter
from .base import AdapterContext, SourceAdapter
from .corporate import AccentureAdapter, CapgeminiAdapter, TcsIbeginAdapter
from .eightfold import EightfoldAdapter
from .html_pages import GenericHtmlAdapter, PaginatedHtmlAdapter
from .linkedin_guest import LinkedInGuestAdapter
from .oracle_hcm import OracleHcmAdapter
from .public_ats import AshbyAdapter, GreenhouseAdapter, LeverAdapter, SmartRecruitersAdapter
from .successfactors import SuccessFactorsAdapter
from .workday import WorkdayAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    cls.name: cls
    for cls in (
        LeverAdapter,
        GreenhouseAdapter,
        AshbyAdapter,
        SmartRecruitersAdapter,
        WorkdayAdapter,
        AmazonJobsAdapter,
        AccentureAdapter,
        CapgeminiAdapter,
        TcsIbeginAdapter,
        SuccessFactorsAdapter,
        PaginatedHtmlAdapter,
        GenericHtmlAdapter,
        OracleHcmAdapter,
        EightfoldAdapter,
        LinkedInGuestAdapter,
    )
}


def adapter_for(source: str, http: HttpClient, context: AdapterContext | None = None) -> SourceAdapter:
    try:
        return ADAPTERS[source](http, context)
    except KeyError:
        raise ValueError(f"No adapter registered for source '{source}'") from None


_SIMPLE_PATTERNS: tuple[tuple[re.Pattern[str], str, dict], ...] = (
    (re.compile(r"^https?://jobs\.eu\.lever\.co/([^/?#]+)", re.I), "lever", {"eu": True}),
    (re.compile(r"^https?://jobs\.lever\.co/([^/?#]+)", re.I), "lever", {}),
    (re.compile(r"^https?://(?:boards|job-boards)\.eu\.greenhouse\.io/([^/?#]+)", re.I), "greenhouse", {"eu": True}),
    (re.compile(r"^https?://(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)", re.I), "greenhouse", {}),
    (re.compile(r"^https?://boards-api\.greenhouse\.io/v1/boards/([^/?#]+)", re.I), "greenhouse", {}),
    (re.compile(r"^https?://jobs\.ashbyhq\.com/([^/?#]+)", re.I), "ashby", {}),
    (re.compile(r"^https?://(?:careers|jobs)\.smartrecruiters\.com/([^/?#]+)", re.I), "smartrecruiters", {}),
)
_WORKDAY_JOBS_RE = re.compile(
    r"^https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)", re.I
)
_WORKDAY_SITE_RE = re.compile(
    r"^https?://([a-z0-9.-]+\.myworkdaysite\.com)/(?:[a-z]{2}-[A-Z]{2}/)?recruiting/([^/?#]+)/([^/?#]+)", re.I
)
_ORACLE_RE = re.compile(
    r"^https?://([a-z0-9.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z]{2}(?:-[A-Z]{2})?/sites/([^/?#]+)", re.I
)
_RESERVED_SEGMENTS = {"wday", "job", "jobs", "details", "embed", "api", "v1", "en-us"}


def board_from_url(url: str) -> Board | None:
    url = (url or "").strip()
    for pattern, source, options in _SIMPLE_PATTERNS:
        match = pattern.match(url)
        if not match:
            continue
        token = match.group(1)
        if token.lower() == "embed":
            token = (parse_qs(urlparse(url).query).get("for") or [""])[0]
        if not token or token.lower() in _RESERVED_SEGMENTS:
            return None
        return Board(company=token, source=source, token=token, options=dict(options))
    match = _WORKDAY_JOBS_RE.match(url)
    if match:
        tenant, pod, site = match.group(1).lower(), match.group(2).lower(), match.group(3)
        if site.lower() in _RESERVED_SEGMENTS:
            return None
        host = f"{tenant}.{pod}.myworkdayjobs.com"
        return Board(company=tenant, source="workday", token=f"{host}|{tenant}|{site}")
    match = _WORKDAY_SITE_RE.match(url)
    if match:
        host, tenant, site = match.group(1).lower(), match.group(2), match.group(3)
        return Board(company=tenant, source="workday", token=f"{host}|{tenant}|{site}")
    match = _ORACLE_RE.match(url)
    if match:
        host, site = match.group(1).lower(), match.group(2)
        return Board(company=host.split(".")[0], source="oracle_hcm", token=f"{host}|{site}")
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host == "careers.ey.com" and parsed.path.startswith("/ey/"):
        return Board(company="EY", source="successfactors", token="https://careers.ey.com/ey/search/?q=analyst&locationsearch=India")
    if host == "apply.careers.microsoft.com":
        return Board(company="Microsoft", source="eightfold", token="apply.careers.microsoft.com|microsoft.com")
    return None


__all__ = ["ADAPTERS", "AdapterContext", "SourceAdapter", "adapter_for", "board_from_url"]
