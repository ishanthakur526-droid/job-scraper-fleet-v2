from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

from .models import Board

_BOARD_FIELDS = {f.name for f in dataclasses.fields(Board)}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _board(item: dict[str, Any]) -> Board:
    return Board(**{key: value for key, value in item.items() if key in _BOARD_FIELDS})


def load_boards(config_dir: Path, include_disabled: bool = False) -> tuple[list[Board], list[str]]:
    data = _read_json(config_dir / "boards.json")
    boards = [_board(item) for item in data.get("boards", [])]
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


def dedupe_boards(boards: list[Board]) -> list[Board]:
    seen: set[str] = set()
    output: list[Board] = []
    for board in boards:
        if board.key in seen:
            continue
        seen.add(board.key)
        output.append(board)
    return output
