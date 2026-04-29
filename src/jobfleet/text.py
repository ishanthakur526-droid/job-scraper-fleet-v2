from __future__ import annotations

import html
import re
from bs4 import BeautifulSoup


INDIA_TERMS = {
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "gurgaon", "gurugram",
    "noida", "hyderabad", "pune", "chennai", "kolkata", "ahmedabad", "remote india"
}

EXCLUDED_TITLE_PATTERNS = (
    r"(?<![a-z0-9])senior(?![a-z0-9])",
    r"(?<![a-z0-9])sr\.?(?![a-z0-9])",
    r"(?<![a-z0-9])lead(?![a-z0-9])",
    r"(?<![a-z0-9])manager(?![a-z0-9])",
    r"(?<![a-z0-9])principal(?![a-z0-9])",
    r"(?<![a-z0-9])staff(?![a-z0-9])",
    r"(?<![a-z0-9])director(?![a-z0-9])",
    r"(?<![a-z0-9])head\s+of(?![a-z0-9])",
    r"(?<![a-z0-9])architect(?![a-z0-9])",
    r"(?<![a-z0-9])avp(?![a-z0-9])",
    r"(?<![a-z0-9])dvp(?![a-z0-9])",
    r"(?<![a-z0-9])vp(?![a-z0-9])",
)


def clean_html(value: str) -> str:
    if not value:
        return ""
    text = BeautifulSoup(html.unescape(value), "html.parser").get_text(" ")
    return normalize_space(text)


def normalize_space(value: str) -> str:
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        value = (value or "").replace(old, new)
    return re.sub(r"\s+", " ", value or "").strip()


def is_india_job(location: str, description: str = "") -> bool:
    location_l = (location or "").lower()
    description_l = (description or "").lower()
    if location_l:
        if any(term in location_l for term in INDIA_TERMS):
            return True
        if "remote" in location_l and "india" in description_l[:1500]:
            return True
        return False
    return any(term in description_l[:1500] for term in INDIA_TERMS)


def contains_negative(text: str, negatives: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in negatives if term.lower() in lowered]


def has_excluded_seniority(title: str) -> bool:
    lowered = title.lower()
    return any(re.search(pattern, lowered) for pattern in EXCLUDED_TITLE_PATTERNS)


def matched_role_terms(title: str, description: str, roles: list[str], positives: list[str]) -> list[str]:
    title_l = title.lower()
    text_l = f"{title} {description[:3000]}".lower()
    matches: list[str] = []
    for role in roles:
        if _title_matches_role(title, role):
            matches.append(role)
    for term in positives:
        if term.lower() in text_l and term not in matches:
            matches.append(term)
    return matches


def role_score(title: str, description: str, roles: list[str], positives: list[str]) -> tuple[int, list[str]]:
    matches = matched_role_terms(title, description, roles, positives)
    score = 0
    for role in roles:
        if _title_matches_role(title, role):
            score += 45
    for term in positives:
        if term.lower() in f"{title} {description[:2500]}".lower():
            score += 5
    return min(score, 100), matches


def _title_matches_role(title: str, role: str) -> bool:
    title_l = title.lower()
    role_l = role.lower()
    if role_l in title_l:
        return True
    title_tokens = set(re.findall(r"[a-z0-9]+", title_l))
    role_tokens = [token for token in re.findall(r"[a-z0-9]+", role_l) if token not in {"and", "of"}]
    if len(role_tokens) <= 2:
        return False
    return bool(role_tokens) and all(token in title_tokens for token in role_tokens)


def parse_experience(description: str) -> tuple[bool, str, str]:
    text = normalize_space(description).lower()
    if not text:
        return True, "Unspecified", "No description text available"

    ranges = []
    for match in re.finditer(r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*(?:\+)?\s*(?:years?|yrs?)", text):
        low, high = int(match.group(1)), int(match.group(2))
        ranges.append((low, high, match.group(0)))

    if ranges:
        allowed = [label for low, _high, label in ranges if low <= 3]
        if allowed:
            return True, allowed[0].replace("yrs", "years"), ""
        return False, ranges[0][2], "Rejected: minimum experience in all detected ranges is above 3 years"

    explicit = []
    for match in re.finditer(r"(?:minimum|min\.?|at least|minimum of)\s*(\d{1,2})\s*(?:\+)?\s*(?:years?|yrs?)", text):
        years = int(match.group(1))
        explicit.append((years, match.group(0), "minimum"))

    for match in re.finditer(r"(\d{1,2})\s*\+\s*(?:years?|yrs?)", text):
        years = int(match.group(1))
        explicit.append((years, match.group(0), "plus"))

    for match in re.finditer(r"(?:more than|over)\s*(\d{1,2})\s*(?:years?|yrs?)", text):
        years = int(match.group(1)) + 1
        explicit.append((years, match.group(0), "strictly-more"))

    if explicit:
        allowed = [label for years, label, _kind in explicit if years <= 3]
        if allowed:
            return True, allowed[0].replace("yrs", "years"), ""
        return False, explicit[0][1], "Rejected: detected explicit minimum above 3 years"

    return True, "Unspecified", ""
