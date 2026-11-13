"""Shared fixtures. Also fails the session if a test writes inside the repo
(v2 tests left hundreds of files under ``job_scraper_fleet_v2/.test_tmp``)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_IGNORED_DIRS = {".git", ".venv", "venv", "outputs", "outputs_dev", "outputs_replay", "outputs_search", "__pycache__", ".pytest_cache", ".ruff_cache"}


def _snapshot() -> set[str]:
    files: set[str] = set()
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
        files.update(os.path.relpath(os.path.join(base, name), ROOT) for name in names)
    return files


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config._repo_snapshot = _snapshot()  # type: ignore[attr-defined]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    before = getattr(session.config, "_repo_snapshot", None)
    if before is None:
        return
    created = sorted(_snapshot() - before)
    if created:
        sys.stderr.write("\nTests wrote files inside the repository: " + ", ".join(created[:10]) + "\n")
        session.exitstatus = 1


class FakeHttp:
    """Minimal stand-in for HttpClient: responses keyed by exact URL or URL prefix."""

    def __init__(self, json_data: dict[str, Any] | None = None, text: dict[str, str] | None = None, post: dict[str, Any] | None = None):
        self.json_data = json_data or {}
        self.text = text or {}
        self.post = post or {}
        self.calls: list[tuple[str, str, Any]] = []
        self.stats: dict[str, int] = {}

    def _lookup(self, table: dict[str, Any], url: str) -> Any:
        if url in table:
            return table[url]
        for key, value in table.items():
            if key.endswith("*") and url.startswith(key[:-1]):
                return value
        raise AssertionError(f"Unexpected URL: {url}")

    def get_json(self, url: str, headers: dict | None = None, timeout: float | None = None) -> Any:
        self.calls.append(("GET", url, None))
        value = self._lookup(self.json_data, url)
        if isinstance(value, Exception):
            raise value
        return value

    def get_text(self, url: str, accept: str = "", headers: dict | None = None, timeout: float | None = None) -> str:
        self.calls.append(("GET", url, None))
        return self._lookup(self.text, url)

    def post_json(self, url: str, payload: Any, headers: dict | None = None, timeout: float | None = None) -> Any:
        self.calls.append(("POST", url, payload))
        value = self._lookup(self.post, url)
        return value(payload) if callable(value) else value

    post_form = post_json


@pytest.fixture
def fake_http():
    return FakeHttp
