from __future__ import annotations

import json
import os
import re
from html import unescape
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from .http import FetchError, HttpClient


ATS_URL_RE = re.compile(
    r"https?://(?:jobs(?:\.eu)?\.lever\.co|boards\.greenhouse\.io|job-boards\.eu\.greenhouse\.io|jobs\.ashbyhq\.com|careers\.smartrecruiters\.com|jobs\.smartrecruiters\.com|[^/]*myworkdayjobs\.com|careers\.ey\.com|careers\.ltimindtree\.com)/[^\s\"'<>]+",
    flags=re.I,
)


def discover_urls(http: HttpClient, queries: list[str], limit_per_query: int = 10) -> list[str]:
    provider = _provider_name()
    urls: list[str] = []
    for query in queries:
        try:
            if provider == "serpapi":
                urls.extend(_serpapi(http, query, limit_per_query))
            elif provider == "brave":
                urls.extend(_brave(http, query, limit_per_query))
            else:
                urls.extend(_free_search(http, query, limit_per_query))
        except FetchError:
            continue
    return _dedupe(urls)


def build_queries(category_name: str, roles: list[str]) -> list[str]:
    role_slice = roles[:4]
    return [
        f'site:jobs.lever.co OR site:boards.greenhouse.io OR site:jobs.ashbyhq.com "{role}" India'
        for role in role_slice
    ] + [
        f'"{category_name}" analyst jobs India greenhouse lever ashby'
    ]


def _provider_name() -> str:
    if os.getenv("SERPAPI_KEY"):
        return "serpapi"
    if os.getenv("BRAVE_SEARCH_API_KEY"):
        return "brave"
    return "duckduckgo"


def _serpapi(http: HttpClient, query: str, limit: int) -> list[str]:
    url = f"https://serpapi.com/search.json?engine=google&num={limit}&q={quote_plus(query)}&api_key={os.environ['SERPAPI_KEY']}"
    data = http.get_json(url)
    return [item["link"] for item in data.get("organic_results", []) if item.get("link")]


def _brave(http: HttpClient, query: str, limit: int) -> list[str]:
    # urllib keeps this project dependency-light; headers are injected with a small
    # direct call because Brave requires a subscription token.
    from urllib.request import Request, urlopen

    req = Request(
        f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(query)}&count={limit}",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"],
            "User-Agent": "job-scraper-fleet-v2/0.1",
        },
    )
    with urlopen(req, timeout=http.timeout) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    return [item["url"] for item in data.get("web", {}).get("results", []) if item.get("url")]


def _duckduckgo(http: HttpClient, query: str, limit: int) -> list[str]:
    html = http.get_text(f"https://duckduckgo.com/html/?q={quote_plus(query)}")
    urls = _extract_ats_urls(html)
    return urls[:limit]


def _bing(http: HttpClient, query: str, limit: int) -> list[str]:
    html = http.get_text(f"https://www.bing.com/search?q={quote_plus(query)}")
    urls = _extract_ats_urls(html)
    return urls[:limit]


def _free_search(http: HttpClient, query: str, limit: int) -> list[str]:
    urls = []
    try:
        urls.extend(_duckduckgo(http, query, limit))
    except FetchError:
        pass
    if len(urls) < limit:
        try:
            urls.extend(_bing(http, query, limit))
        except FetchError:
            pass
    return _dedupe(urls)[:limit]


def _extract_ats_urls(html: str) -> list[str]:
    text = unescape(html)
    urls = ATS_URL_RE.findall(text)
    for href in re.findall(r'href=["\']([^"\']+)["\']', html):
        decoded = unescape(href)
        parsed = urlparse(decoded)
        target = ""
        if parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
        elif parsed.path.startswith("/ck/a") or parsed.path.startswith("/url"):
            target = parse_qs(parsed.query).get("u", [""])[0]
        if target:
            urls.extend(ATS_URL_RE.findall(unquote(target)))
        else:
            urls.extend(ATS_URL_RE.findall(decoded))
    return _dedupe(urls)


def _dedupe(urls: list[str]) -> list[str]:
    seen = set()
    output = []
    for url in urls:
        normalized = url.rstrip(").,")
        if normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output
