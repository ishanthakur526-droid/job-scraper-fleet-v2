"""Search profile: the single file a user edits to retarget JobFleet.

``profile.toml`` describes WHERE (countries, cities, remote), the LEVEL
(years of experience + a seniority preset) and WHAT (one or more role
families). Everything the engine needs - title rules, keyword lists, search
terms for each source, Claude prompts - is derived from it.
"""

from __future__ import annotations

import difflib
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .geo import country_code, country_names
from .levels import ACTIONS, ALL_LEVEL_NAMES, DEFAULT_YEARS, DOMAINS, LEVEL_PRESETS, level_actions
from .models import Category

REMOTE_POLICIES = ("include", "only", "exclude")
GENERIC_ABBREVIATIONS = {"sr": "senior", "jr": "junior", "assoc": "associate", "exec": "executive", "mgr": "manager", "ops": "operations"}
GENERIC_POSSIBLE_TERMS = frozenset({"analyst", "associate", "specialist", "executive", "consultant", "coordinator", "officer"})
_STOP = frozenset(
    {"and", "of", "the", "for", "a", "an", "in", "to", "with", "i", "ii", "iii", "iv", "senior", "junior", "lead", "manager",
     "head", "director", "staff", "principal", "chief", "vice", "president", "intern", "trainee"}
)
DEFAULT_AI: dict[str, Any] = {
    "enabled": True,
    "claude_exe": "",
    "model": "sonnet",
    "effort": "low",
    "isolate_settings": True,
    "scout": {"enabled": True, "every_days": 7, "timeout_s": 900, "model": "sonnet", "effort": "medium"},
    "triage": {"enabled": True, "max_items": 60, "timeout_s": 240, "promote_confidence": 0.75, "demote_confidence": 0.85},
}


class ProfileError(ValueError):
    """A problem in profile.toml, phrased for a non-technical reader."""


@dataclass(frozen=True)
class Rules:
    level_actions: dict[str, str]
    senior_only_for: tuple[str, ...]
    excluded_domains: tuple[str, ...]
    prefilter_terms: frozenset[str]
    possible_terms: frozenset[str]
    tie_priority: dict[str, int]
    abbreviations: dict[str, str]


@dataclass
class Profile:
    name: str
    countries: list[str]
    cities: list[str]
    remote: str
    min_years: float
    max_years: float
    level: str
    families: list[Category]
    adjacent: Category | None
    search_keywords: list[str]
    rules: Rules
    ai: dict[str, Any]
    path: Path | None = None
    country_codes: list[str] = field(default_factory=list)

    @property
    def family_ids(self) -> list[str]:
        return [f.id for f in self.families]

    def describe(self) -> str:
        years = f"{_fmt(self.min_years)}-{_fmt(self.max_years)} years"
        return f"{', '.join(f.name for f in self.families)} | {self.where_text()} | {years} ({self.level.replace('_', ' ')})"

    # ---- plain-English pieces used in Claude prompts and reports
    def where_text(self) -> str:
        place = ", ".join(self.countries) or "anywhere"
        if self.cities:
            place = f"{', '.join(self.cities)} ({place})"
        remote = {"include": " or remote", "only": " - remote jobs only", "exclude": " - on-site/hybrid only, no fully remote jobs"}[self.remote]
        return place + remote if self.countries else "remote jobs anywhere"

    def experience_text(self) -> str:
        low, high = _fmt(self.min_years), _fmt(self.max_years)
        over = _fmt(self.max_years + 1)
        text = (
            f"the job must accept someone with {low}-{high} years of experience (overlapping ranges are fine; "
            f"a strict minimum of {over}+ years is not"
        )
        if self.min_years > 0:
            text += f"; roles capped below {low} years are too junior"
        return text + ")."

    def families_text(self) -> str:
        lines = [f"- {f.id}: {', '.join(_title_strings(f))}." for f in self.families]
        if self.adjacent:
            lines.append(f"- adjacent: {', '.join(_title_strings(self.adjacent))} (acceptable but secondary).")
        return "\n".join(lines)

    def not_wanted_text(self) -> str:
        from .levels import LEVELS

        levels = [LEVELS[n].description.lower() for n, a in self.rules.level_actions.items() if a == "exclude" and n in LEVELS]
        domains = [DOMAINS[d].description.lower() for d in self.rules.excluded_domains if d in DOMAINS]
        return "; ".join(x for x in (", ".join(levels), ", ".join(domains)) if x)

    def conditional_text(self) -> str:
        """Seniority words that are fine when the posting's experience range fits (e.g. "Deputy Manager" for 0-3 years)."""
        from .levels import LEVEL_3_PLUS, LEVELS

        parts = []
        for name, action in self.rules.level_actions.items():
            if action != "conditional":
                continue
            if name == LEVEL_3_PLUS:
                parts.append("level III and above titles (e.g. Analyst III)")
            elif name == "senior" and self.rules.senior_only_for:
                parts.append(f"Senior {'/'.join(w.title() for w in self.rules.senior_only_for)} titles")
            elif name in LEVELS:
                parts.append(LEVELS[name].description)
        return "; ".join(parts)


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def default_profile_path(config_dir: Path) -> Path:
    return config_dir.resolve().parent / "profile.toml"


def load_profile(path: Path) -> Profile:
    if not path.exists():
        raise ProfileError(
            f"No profile found at {path}.\nCreate one by double-clicking Setup.bat (or running `jobfleet setup`), "
            "or copy one of the examples in the profiles/ folder to profile.toml."
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path.name} has a formatting mistake: {exc}.\nCheck quotes, commas and [section] names near that line.") from None
    profile = profile_from_dict(data)
    profile.path = path
    return profile


def profile_from_dict(data: dict[str, Any]) -> Profile:
    problems: list[str] = []
    location = _table(data, "location", problems)
    experience = _table(data, "experience", problems)
    advanced = _table(data, "advanced", problems)

    countries = [str(c).strip() for c in _list(location, "countries", problems) if str(c).strip()]
    cities = [str(c).strip() for c in _list(location, "cities", problems) if str(c).strip()]
    remote = str(location.get("remote", "include")).strip().lower()
    if remote not in REMOTE_POLICIES:
        problems.append(f"[location] remote must be one of {', '.join(REMOTE_POLICIES)} (got '{remote}').")
    if not countries and remote != "only":
        problems.append("[location] countries is empty. Add at least one country, e.g. countries = [\"India\"] (or set remote = \"only\").")
    country_codes: list[str] = []
    for country in countries:
        code = country_code(country)
        if code:
            country_codes.append(code)
            continue
        guess = closest(country, country_names() + ["USA", "UK", "UAE"])
        hint = f" Did you mean '{guess}'?" if guess else " Use the English country name, e.g. \"Germany\"."
        problems.append(f"[location] '{country}' is not a country I know.{hint}")

    level = str(experience.get("level", "early_career")).strip().lower()
    if level not in LEVEL_PRESETS:
        problems.append(f"[experience] level must be one of {', '.join(LEVEL_PRESETS)} (got '{level}').")
        level = "early_career"
    default_min, default_max = DEFAULT_YEARS[level]
    min_years = _number(experience, "min_years", default_min, problems)
    max_years = _number(experience, "max_years", default_max, problems)
    if min_years > max_years:
        problems.append(f"[experience] min_years ({_fmt(min_years)}) is larger than max_years ({_fmt(max_years)}).")

    families = [_family(item, index, problems) for index, item in enumerate(data.get("role_family") or [])]
    families = [f for f in families if f]
    if not families:
        problems.append("Add at least one [[role_family]] with a name and a list of job titles.")
    ids = [f.id for f in families]
    for dup in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"Two role families share the id '{dup}'. Give each a different id.")
    adjacent = None
    if isinstance(data.get("adjacent"), dict) and data["adjacent"].get("titles"):
        adjacent = _family({"id": "adjacent", "name": "Adjacent roles (review)", "output": "adjacent_roles_today.csv", **data["adjacent"]}, -1, problems, route="adjacent")

    overrides = dict(advanced.get("levels") or {})
    for lvl in advanced.get("exclude_levels") or []:
        overrides[str(lvl)] = "exclude"
    for lvl in advanced.get("allow_levels") or []:
        overrides[str(lvl)] = "allow"
    for lvl in advanced.get("conditional_levels") or []:
        overrides[str(lvl)] = "conditional"
    for name, action in overrides.items():
        if name not in ALL_LEVEL_NAMES:
            problems.append(f"[advanced] unknown level '{name}'. Known levels: {', '.join(ALL_LEVEL_NAMES)}.")
        if action not in ACTIONS:
            problems.append(f"[advanced] level '{name}' must be allow, conditional or exclude (got '{action}').")

    all_cats = families + ([adjacent] if adjacent else [])
    allow_domains = [str(d) for d in advanced.get("allow_domains") or []]
    excluded = advanced.get("exclude_domains")
    for name in {d for c in all_cats for d in c.domains} | set(allow_domains) | set(excluded or []):
        if name not in DOMAINS:
            problems.append(f"Unknown domain '{name}'. Known domains: {', '.join(DOMAINS)}.")
    for fid in advanced.get("tie_priority") or []:
        if fid not in ids:
            problems.append(f"[advanced] tie_priority mentions '{fid}', which is not the id of a role family ({', '.join(ids)}).")
    search_keywords = [str(k) for k in (_table(data, "search", problems).get("keywords") or [])] or _derived_search(families)

    if problems:
        raise ProfileError("profile.toml needs a fix:\n- " + "\n- ".join(problems))

    rules = default_rules(all_cats, level, overrides=overrides, allow_domains=allow_domains)
    rules = Rules(
        level_actions=rules.level_actions,
        senior_only_for=tuple(str(n).lower() for n in advanced.get("senior_only_for") or ()),
        excluded_domains=tuple(excluded) if excluded is not None else rules.excluded_domains,
        prefilter_terms=frozenset(str(t).lower() for t in advanced["prefilter_terms"]) if advanced.get("prefilter_terms") else rules.prefilter_terms,
        possible_terms=frozenset(str(t).lower() for t in advanced["possible_terms"]) if advanced.get("possible_terms") else rules.possible_terms,
        tie_priority=_tie_priority(list(advanced.get("tie_priority") or []) + [i for i in ids if i not in (advanced.get("tie_priority") or [])]),
        abbreviations={**GENERIC_ABBREVIATIONS, **{str(k).lower(): str(v).lower() for k, v in (advanced.get("title_abbreviations") or {}).items()}},
    )

    ai = json.loads(json.dumps(DEFAULT_AI))
    for key, value in (data.get("ai") or {}).items():
        if isinstance(value, dict) and isinstance(ai.get(key), dict):
            ai[key].update(value)
        else:
            ai[key] = value

    return Profile(
        name=str(data.get("name") or "My job search"),
        countries=countries,
        cities=cities,
        remote=remote,
        min_years=min_years,
        max_years=max_years,
        level=level,
        families=families,
        adjacent=adjacent,
        search_keywords=search_keywords,
        rules=rules,
        ai=ai,
        country_codes=list(dict.fromkeys(country_codes)),
    )


def default_rules(
    categories: list[Category],
    level: str = "early_career",
    *,
    overrides: dict[str, str] | None = None,
    allow_domains: list[str] | None = None,
) -> Rules:
    """Rules derived from the role families alone (what a profile without an [advanced] section gets)."""
    owned = {d for c in categories for d in c.domains} | set(allow_domains or [])
    terms = _derived_terms(categories)
    return Rules(
        level_actions=level_actions(level, overrides),
        senior_only_for=(),
        excluded_domains=tuple(d for d in DOMAINS if d not in owned),
        prefilter_terms=frozenset(terms),
        possible_terms=frozenset(terms | GENERIC_POSSIBLE_TERMS),
        tie_priority=_tie_priority([c.id for c in categories if c.route == "main"]),
        abbreviations=dict(GENERIC_ABBREVIATIONS),
    )


def _tie_priority(order: list[str]) -> dict[str, int]:
    priority = {fid: (len(order) - i) * 100 for i, fid in enumerate(order)}
    priority["adjacent"] = 0
    return priority


def _table(data: dict[str, Any], key: str, problems: list[str]) -> dict[str, Any]:
    value = data.get(key) or {}
    if not isinstance(value, dict):
        problems.append(f"[{key}] should be a section, like [{key}].")
        return {}
    return value


def _list(table: dict[str, Any], key: str, problems: list[str]) -> list[Any]:
    value = table.get(key) or []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        problems.append(f"'{key}' should be a list, like {key} = [\"...\"].")
        return []
    return value


def _number(table: dict[str, Any], key: str, default: float, problems: list[str]) -> float:
    value = table.get(key, default)
    try:
        number = float(value)
    except (TypeError, ValueError):
        problems.append(f"[experience] {key} should be a number (got '{value}').")
        return float(default)
    if number < 0 or number > 50:
        problems.append(f"[experience] {key} should be between 0 and 50 (got {value}).")
    return number


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "family"


def _family(item: Any, index: int, problems: list[str], route: str = "main") -> Category | None:
    where = f"role family #{index + 1}" if index >= 0 else "[adjacent]"
    if not isinstance(item, dict):
        problems.append(f"{where} should be a [[role_family]] section.")
        return None
    name = str(item.get("name") or "").strip()
    titles = item.get("titles") or []
    if not name and route == "main":
        problems.append(f"{where} needs a name, e.g. name = \"Data & BI\".")
    if not titles:
        problems.append(f"{where} ('{name or '?'}') needs at least one job title in titles = [...].")
    for title in titles:
        if not (isinstance(title, str) or (isinstance(title, dict) and title.get("title"))):
            problems.append(f"{where}: titles must be text like \"Data Analyst\" (got {title!r}).")
    family_id = str(item.get("id") or slug(name))
    return Category(
        id=family_id,
        name=name or family_id,
        output=str(item.get("output") or f"{family_id}_jobs_today.csv"),
        target_roles=list(titles),
        positive_keywords=[str(k) for k in item.get("keywords") or []],
        negative_keywords=[str(k) for k in item.get("exclude_title_words") or []],
        negative_description_phrases=[str(k) for k in item.get("exclude_description_phrases") or []],
        excluded_title_patterns=[str(k) for k in item.get("exclude_title_patterns") or []],
        title_keywords=[str(k) for k in item.get("title_keywords") or []],
        route=route,
        domains=[str(d) for d in item.get("domains") or []],
    )


def _title_strings(category: Category) -> list[str]:
    return [str(t["title"]) if isinstance(t, dict) else str(t) for t in category.target_roles]


def _derived_terms(categories: list[Category]) -> set[str]:
    terms: set[str] = set()
    for category in categories:
        for text in _title_strings(category) + category.title_keywords:
            terms.update(tok for tok in re.findall(r"[a-z0-9+#]+", text.lower()) if tok not in _STOP and len(tok) > 1)
    return terms


def _derived_search(families: list[Category]) -> list[str]:
    seen: dict[str, None] = {}
    for family in families:
        for title in _title_strings(family)[:4]:
            seen.setdefault(title.lower(), None)
    return list(seen)[:12]


def closest(word: str, options: list[str]) -> str:
    match = difflib.get_close_matches(word.lower(), [o.lower() for o in options], n=1, cutoff=0.75)
    if not match:
        return ""
    return next(o for o in options if o.lower() == match[0])
