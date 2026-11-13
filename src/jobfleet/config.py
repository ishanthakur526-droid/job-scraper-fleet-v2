from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from .models import Board

_BOARD_FIELDS = {f.name for f in dataclasses.fields(Board)}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _board(item: dict[str, Any]) -> Board:
    return Board(**{key: value for key, value in item.items() if key in _BOARD_FIELDS})


def load_boards(config_dir: Path, include_disabled: bool = False) -> tuple[list[Board], list[str]]:
    """Companies to check: config/companies.json (v3 name: boards.json) plus scout/discovery finds."""
    path = config_dir / "companies.json"
    if not path.exists():
        path = config_dir / "boards.json"
    data = _read_json(path)
    boards = [_board(item) for item in data.get("companies", data.get("boards", []))]
    discovered_path = config_dir / "discovered_boards.json"
    if discovered_path.exists():
        boards.extend(_board(item) for item in _read_json(discovered_path).get("boards", []))
    boards = dedupe_boards(boards)
    if not include_disabled:
        boards = [board for board in boards if board.enabled]
    return boards, list(data.get("seed_urls", []))


def write_discovered_boards(config_dir: Path, boards: list[Board]) -> Path:
    path = config_dir / "discovered_boards.json"
    data = {
        "boards": [
            {
                "company": board.company,
                "source": board.source,
                "token": board.token,
                "priority_categories": board.priority_categories,
                **({"note": board.note} if board.note else {}),
            }
            for board in dedupe_boards(boards)
        ]
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_discovered_boards(config_dir: Path) -> list[Board]:
    path = config_dir / "discovered_boards.json"
    if not path.exists():
        return []
    return [_board(item) for item in _read_json(path).get("boards", [])]


def expand_boards(boards: list[Board], countries: list[str] | tuple[str, ...], keywords: list[str] | tuple[str, ...]) -> list[Board]:
    """Fit the company list to a profile.

    - an entry with ``countries`` (e.g. an India-only careers site) is skipped unless the profile looks there
    - ``{keyword}`` in the token or options becomes one entry per profile search keyword (``max_keywords``, default 3)
    - ``{country}`` becomes one entry per profile country name (at most 3)
    """
    from .geo import country_name

    wanted = {c.upper() for c in countries}
    names = [country_name(c) for c in countries][:3] or [""]
    output: list[Board] = []
    for board in boards:
        if board.countries and wanted and not wanted & {c.upper() for c in board.countries}:
            continue
        variants = [board]
        if _mentions(board, "{keyword}"):
            limit = int(board.options.get("max_keywords", 3))
            variants = [_fill(b, "{keyword}", kw) for b in variants for kw in list(keywords)[:limit]]
        if _mentions(board, "{country}"):
            variants = [_fill(b, "{country}", name) for b in variants for name in names]
        output.extend(variants)
    return dedupe_boards(output)


def _mentions(board: Board, placeholder: str) -> bool:
    return placeholder in board.token or placeholder in json.dumps(board.options)


def _fill(board: Board, placeholder: str, value: str) -> Board:
    options = json.loads(json.dumps(board.options).replace(placeholder, json.dumps(value)[1:-1]))
    token = board.token.replace(placeholder, quote_plus(value) if board.token.startswith("http") else value)
    return dataclasses.replace(board, token=token, options=options)


def dedupe_boards(boards: list[Board]) -> list[Board]:
    seen: set[str] = set()
    output: list[Board] = []
    for board in boards:
        if board.key in seen:
            continue
        seen.add(board.key)
        output.append(board)
    return output
