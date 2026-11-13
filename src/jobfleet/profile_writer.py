"""Write a commented profile.toml from a few choices (used by the wizard, the
GitHub setup form and scripts/make_presets.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .levels import DEFAULT_YEARS
from .profile import slug
from .role_library import FAMILIES


@dataclass
class Choices:
    name: str
    countries: list[str]
    families: list[str]  # role-library ids
    level: str = "early_career"
    min_years: float | None = None
    max_years: float | None = None
    cities: list[str] = field(default_factory=list)
    remote: str = "include"
    extra_titles: list[str] = field(default_factory=list)  # added to the first family
    custom_family: str = ""  # name for a family made only of extra_titles
    exclude_title_words: list[str] = field(default_factory=list)
    ai: bool = True


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _list(values: list[str], indent: int = 0, width: int = 110) -> str:
    items = [_q(v) for v in values]
    one_line = "[" + ", ".join(items) + "]"
    if len(one_line) + indent <= width:
        return one_line
    lines, current = [], "  "
    for item in items:
        if len(current) + len(item) + 2 > width:
            lines.append(current.rstrip())
            current = "  "
        current += item + ", "
    lines.append(current.rstrip())
    return "[\n" + "\n".join(lines) + "\n]"


def _years(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def render(choices: Choices) -> str:
    low, high = DEFAULT_YEARS[choices.level]
    min_years = low if choices.min_years is None else choices.min_years
    max_years = high if choices.max_years is None else choices.max_years
    out = [
        "# ─────────────────────────────────────────────────────────────────────────────",
        "#  JobFleet search profile — this one file decides WHERE you look, at what",
        "#  LEVEL, and for WHICH roles. Edit it in any text editor, save, run again.",
        "#  Re-create it any time with Setup.bat (or `jobfleet setup`).",
        "# ─────────────────────────────────────────────────────────────────────────────",
        "",
        f"name = {_q(choices.name)}",
        "",
        "# ── WHERE ──",
        "[location]",
        f"countries = {_list(choices.countries)}",
        f"cities    = {_list(choices.cities)}   # optional: only these cities (remote jobs still count)",
        f"remote    = {_q(choices.remote)}   # include | only | exclude",
        "",
        "# ── LEVEL ──",
        "[experience]",
        f"min_years = {_years(min_years)}",
        f"max_years = {_years(max_years)}",
        f"level     = {_q(choices.level)}   # student | early_career | mid | senior | leadership",
        "",
        "# ── WHAT ── one [[role_family]] per kind of job; each gets its own list and dashboard tab.",
        "# Add titles freely (word order does not matter). Delete a block to drop that family.",
    ]
    abbreviations: dict[str, str] = {}
    search: list[str] = []
    for index, fid in enumerate(choices.families):
        info = FAMILIES[fid]
        titles = list(info["titles"]) + (choices.extra_titles if index == 0 and not choices.custom_family else [])
        out += [
            "",
            "[[role_family]]",
            f"id     = {_q(fid)}",
            f"name   = {_q(info['name'])}",
            f"titles = {_list(titles)}",
            f"title_keywords = {_list(info['title_keywords'])}",
            f"keywords = {_list(info['keywords'])}",
        ]
        if info["domains"]:
            out.append(f"domains = {_list(info['domains'])}   # job areas this family covers (otherwise filtered out)")
        if choices.exclude_title_words:
            out.append(f"exclude_title_words = {_list(choices.exclude_title_words)}")
        abbreviations.update(info.get("abbreviations", {}))
        search += [s for s in info["search"] if s not in search]
    if choices.custom_family and choices.extra_titles:
        out += [
            "",
            "[[role_family]]",
            f"id     = {_q(slug(choices.custom_family))}",
            f"name   = {_q(choices.custom_family)}",
            f"titles = {_list(choices.extra_titles)}",
        ]
        search += [t.lower() for t in choices.extra_titles[:2]]
    out += [
        "",
        "# Words typed into job-board search boxes (only some sources need them).",
        "[search]",
        f"keywords = {_list(search[:6])}",
        "",
        "# ── OPTIONAL: Claude (your Claude subscription via the Claude Code CLI; no API key) ──",
        "[ai]",
        f"enabled = {'true' if choices.ai else 'false'}",
    ]
    if abbreviations:
        out += ["", "[advanced.title_abbreviations]   # shorthands expanded in job titles"]
        out += [f"{key} = {_q(value)}" for key, value in abbreviations.items()]
    return "\n".join(out) + "\n"
