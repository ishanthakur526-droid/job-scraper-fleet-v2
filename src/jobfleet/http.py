"""HTTP transport for the fleet.

Uses curl_cffi with a Chrome TLS/HTTP2 fingerprint (several career sites reset
plain urllib connections), one session per thread, a polite per-host
concurrency limit, and a retry policy that only retries transient failures.
Falls back to urllib when curl_cffi is not installed.
"""

from __future__ import annotations

import json
import logging
import random
import re
import socket
import threading
import time
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator
from urllib.parse import urlencode, urlparse

log = logging.getLogger(__name__)

try:  # pragma: no cover - import guard
    from curl_cffi import requests as _curl
    from curl_cffi.requests import exceptions as _curl_exc
except Exception:  # pragma: no cover - exercised only without curl_cffi
    _curl = None
    _curl_exc = None


RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
HARD_STATUS = frozenset({404, 406, 410})
DEFAULT_ACCEPT = "application/json, text/html;q=0.9, */*;q=0.8"
_SECRET_RE = re.compile(
    r"(?i)([?&;](?:api[_-]?key|key|token|access_token|auth|signature|sig|password|secret)=)[^&#\s'\"]+"
)


def redact(text: str) -> str:
    """Remove secret-looking query parameters from URLs/messages."""
    return _SECRET_RE.sub(r"\1REDACTED", text or "")


class FetchError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False, hard: bool = False):
        super().__init__(redact(message))
        self.status = status
        self.retryable = retryable
        self.hard = hard


@dataclass
class HttpResponse:
    status: int
    url: str
    text: str
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return json.loads(self.text)


class HttpClient:
    """Thread-safe HTTP client with the same small surface the adapters use."""

    def __init__(
        self,
        timeout: float = 25.0,
        retries: int = 2,
        backoff: float = 0.8,
        max_retry_after: float = 60.0,
        per_host: int = 3,
        min_interval: float = 0.3,
        impersonate: str = "chrome",
        family_limits: dict[str, int] | None = None,
    ):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_retry_after = max_retry_after
        self.per_host = per_host
        self.min_interval = min_interval
        self.impersonate = impersonate
        self._local = threading.local()
        self._lock = threading.Lock()
        self._host_sems: dict[str, threading.BoundedSemaphore] = {}
        self._family_sems = {
            suffix: threading.BoundedSemaphore(limit)
            for suffix, limit in (family_limits or {"myworkdayjobs.com": 6, "myworkdaysite.com": 6}).items()
        }
        self._next_slot: dict[str, float] = {}
        self.stats: Counter[str] = Counter()

    # ------------------------------------------------------------------ public
    def get_text(self, url: str, accept: str = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8", headers: dict[str, str] | None = None, timeout: float | None = None) -> str:
        return self.request("GET", url, accept=accept, headers=headers, timeout=timeout).text

    def get_json(self, url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> Any:
        return _decode_json(self.request("GET", url, accept="application/json", headers=headers, timeout=timeout), url)

    def post_json(self, url: str, payload: Any, headers: dict[str, str] | None = None, timeout: float | None = None) -> Any:
        return _decode_json(self.request("POST", url, json_body=payload, accept="application/json", headers=headers, timeout=timeout), url)

    def post_form(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: float | None = None) -> Any:
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
        hdrs.update(headers or {})
        return _decode_json(
            self.request("POST", url, data=urlencode(payload), accept="application/json", headers=hdrs, timeout=timeout),
            url,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: str | bytes | None = None,
        json_body: Any = None,
        accept: str | None = None,
        timeout: float | None = None,
        allow_redirects: bool = True,
        raise_for_status: bool = True,
        retries: int | None = None,
    ) -> HttpResponse:
        host = (urlparse(url).hostname or "").lower()
        attempts = max(1, (self.retries if retries is None else retries) + 1)
        last_error: FetchError | None = None
        for attempt in range(attempts):
            delay = 0.0
            with self._host_slot(host):
                self._wait_turn(host)
                try:
                    response = self._send(method, url, headers, data, json_body, accept, timeout, allow_redirects)
                except FetchError as exc:
                    last_error = exc
                    if not exc.retryable or attempt == attempts - 1:
                        raise
                    delay = self._backoff_delay(attempt)
                else:
                    self.stats[host] += 1
                    if 200 <= response.status < 300:
                        return response
                    retryable = response.status in RETRYABLE_STATUS
                    if not raise_for_status and not retryable:
                        return response
                    error = FetchError(
                        f"HTTP {response.status} for {method} {url}",
                        status=response.status,
                        retryable=retryable,
                        hard=response.status in HARD_STATUS,
                    )
                    if not retryable or attempt == attempts - 1:
                        if not raise_for_status:
                            return response
                        raise error
                    last_error = error
                    delay = _retry_after(response.headers, self.max_retry_after) or self._backoff_delay(attempt)
            time.sleep(delay)
        assert last_error is not None
        raise last_error

    def cookies(self, domain: str = "") -> dict[str, str]:
        """Cookies held by this thread's session, optionally only those for ``domain``.

        Scoped by domain because several sites set same-named cookies (e.g. XSRF-TOKEN).
        """
        session = getattr(self._local, "session", None)
        if session is None:
            return {}
        try:
            jar = session.cookies.jar
            return {c.name: c.value or "" for c in jar if not domain or c.domain.lstrip(".").endswith(domain)}
        except Exception:  # pragma: no cover - cookie jar API differences
            return {}

    # ----------------------------------------------------------------- helpers
    def _backoff_delay(self, attempt: int) -> float:
        return self.backoff * (2**attempt) + random.uniform(0, self.backoff)

    @contextmanager
    def _host_slot(self, host: str) -> Iterator[None]:
        with self._lock:
            sem = self._host_sems.get(host)
            if sem is None:
                sem = self._host_sems[host] = threading.BoundedSemaphore(self.per_host)
        family = [s for suffix, s in self._family_sems.items() if host.endswith(suffix)]
        with ExitStack() as stack:
            for item in family:
                stack.enter_context(item)
            stack.enter_context(sem)
            yield

    def _wait_turn(self, host: str) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot.get(host, 0.0))
            self._next_slot[host] = slot + self.min_interval
        wait = slot - now
        if wait > 0:
            time.sleep(wait)

    def _session(self):
        session = getattr(self._local, "session", None)
        if session is None:
            session = _curl.Session(impersonate=self.impersonate)
            self._local.session = session
        return session

    def _send(self, method, url, headers, data, json_body, accept, timeout, allow_redirects) -> HttpResponse:
        hdrs = {"Accept": accept or DEFAULT_ACCEPT, "Accept-Language": "en-US,en;q=0.9"}
        hdrs.update(headers or {})
        if _curl is None:
            return _urllib_send(method, url, hdrs, data, json_body, timeout or self.timeout, allow_redirects)
        kwargs: dict[str, Any] = {
            "headers": hdrs,
            "timeout": timeout or self.timeout,
            "allow_redirects": allow_redirects,
        }
        if json_body is not None:
            kwargs["json"] = json_body
        elif data is not None:
            kwargs["data"] = data
        try:
            response = self._session().request(method, url, **kwargs)
        except _curl_exc.DNSError as exc:  # retried (resolver blips happen); counts as hard if it persists
            raise FetchError(f"DNS lookup failed for {url}: {exc}", hard=True, retryable=True) from None
        except _curl_exc.Timeout as exc:
            raise FetchError(f"Timeout for {method} {url}: {exc}", retryable=True) from None
        except _curl_exc.RequestException as exc:
            raise FetchError(f"Connection error for {method} {url}: {exc}", retryable=True) from None
        return HttpResponse(
            status=int(response.status_code),
            url=str(response.url),
            text=response.text or "",
            headers={str(k).lower(): str(v) for k, v in response.headers.items()},
        )


class OfflineHttpClient(HttpClient):
    """Used by --replay: any network access is a bug."""

    def request(self, method: str, url: str, **_kwargs: Any) -> HttpResponse:  # type: ignore[override]
        raise FetchError(f"offline replay mode: refused {method} {url}")


def _decode_json(response: HttpResponse, url: str) -> Any:
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        snippet = response.text[:120].replace("\n", " ")
        raise FetchError(f"Invalid JSON from {url}: {exc}; body starts {snippet!r}") from None


def _retry_after(headers: dict[str, str], cap: float) -> float:
    value = (headers or {}).get("retry-after", "")
    try:
        return min(float(value), cap)
    except (TypeError, ValueError):
        return 0.0


def _urllib_send(method, url, headers, data, json_body, timeout, allow_redirects) -> HttpResponse:  # pragma: no cover
    from http.client import HTTPException
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    body = None
    headers = dict(headers)
    headers.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jobfleet/3")
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif data is not None:
        body = data.encode("utf-8") if isinstance(data, str) else data
    req = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return HttpResponse(response.status, response.geturl(), response.read().decode(charset, "replace"), {k.lower(): v for k, v in response.headers.items()})
    except HTTPError as exc:
        text = exc.read().decode("utf-8", "replace") if exc.fp else ""
        return HttpResponse(exc.code, url, text, {k.lower(): v for k, v in (exc.headers or {}).items()})
    except URLError as exc:
        if isinstance(exc.reason, socket.gaierror):
            raise FetchError(f"DNS lookup failed for {url}: {exc.reason}", hard=True, retryable=True) from None
        raise FetchError(f"Connection error for {method} {url}: {exc.reason}", retryable=True) from None
    except (TimeoutError, socket.timeout) as exc:
        raise FetchError(f"Timeout for {method} {url}: {exc}", retryable=True) from None
    except (ConnectionError, HTTPException) as exc:
        raise FetchError(f"Connection error for {method} {url}: {exc}", retryable=True) from None
