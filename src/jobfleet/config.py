from __future__ import annotations

import json
from pathlib import Path

from .models import Board, Category


def load_categories(config_dir: Path) -> list[Category]:
    data = json.loads((config_dir / "categories.json").read_text(encoding="utf-8"))
    return [Category(**item) for item in data["categories"]]


def load_boards(config_dir: Path) -> tuple[list[Board], list[str]]:
    data = json.loads((config_dir / "boards.json").read_text(encoding="utf-8"))
    boards = [Board(**item) for item in data.get("boards", [])]
    discovered_path = config_dir / "discovered_boards.json"
    if discovered_path.exists():
        discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
        boards.extend(Board(**item) for item in discovered.get("boards", []))
    seed_urls = list(data.get("seed_urls", []))
    return dedupe_boards(boards), seed_urls


def write_discovered_boards(config_dir: Path, boards: list[Board]) -> Path:
    path = config_dir / "discovered_boards.json"
    data = {
        "boards": [
            {
                "company": board.company,
                "source": board.source,
                "token": board.token,
                "priority_categories": board.priority_categories,
            }
            for board in dedupe_boards(boards)
        ]
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_discovered_boards(config_dir: Path) -> list[Board]:
    path = config_dir / "discovered_boards.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Board(**item) for item in data.get("boards", [])]


def dedupe_boards(boards: list[Board]) -> list[Board]:
    seen = set()
    output = []
    for board in boards:
        key = (board.source.lower(), board.token.lower())
        if key in seen:
            continue
        seen.add(key)
        output.append(board)
    return output
