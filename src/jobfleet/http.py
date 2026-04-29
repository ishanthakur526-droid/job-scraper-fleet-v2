from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class FetchError(RuntimeError):
    pass


@dataclass
class HttpClient:
    timeout: int = 25
    retries: int = 2
    pause_seconds: float = 0.35

    def get_text(self, url: str, accept: str = "text/html,application/json") -> str:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                req = Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 job-scraper-fleet-v2/0.1",
                        "Accept": accept,
                    },
                )
                with urlopen(req, timeout=self.timeout) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return response.read().decode(charset, errors="replace")
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.pause_seconds * (attempt + 1))
        raise FetchError(f"Unable to fetch {url}: {last_error}")

    def get_json(self, url: str) -> object:
        return json.loads(self.get_text(url, accept="application/json"))

    def post_json(self, url: str, payload: object, headers: dict[str, str] | None = None) -> object:
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request_headers = {
                    "User-Agent": "Mozilla/5.0 job-scraper-fleet-v2/0.1",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
                request_headers.update(headers or {})
                req = Request(
                    url,
                    data=body,
                    method="POST",
                    headers=request_headers,
                )
                with urlopen(req, timeout=self.timeout) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return json.loads(response.read().decode(charset, errors="replace"))
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.pause_seconds * (attempt + 1))
        raise FetchError(f"Unable to post {url}: {last_error}")

    def post_form(self, url: str, payload: dict[str, object], headers: dict[str, str] | None = None) -> object:
        body = urlencode(payload).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request_headers = {
                    "User-Agent": "Mozilla/5.0 job-scraper-fleet-v2/0.1",
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                request_headers.update(headers or {})
                req = Request(
                    url,
                    data=body,
                    method="POST",
                    headers=request_headers,
                )
                with urlopen(req, timeout=self.timeout) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return json.loads(response.read().decode(charset, errors="replace"))
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.pause_seconds * (attempt + 1))
        raise FetchError(f"Unable to post form {url}: {last_error}")
