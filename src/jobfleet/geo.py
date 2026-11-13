"""Decide whether a job is located in India.

Order of evidence: structured country codes from the ATS, then the location
text split into segments (multi-location postings count if any segment is in
India), then - only when the location is empty/unknown - strict phrases in the
description. Matching is word-boundary based, so "Indiana", "Indianapolis" and
"Indian Wells" never look like India.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

from .geo_data import (
    AMBIGUOUS_INDIAN_CITIES,
    FOREIGN_COUNTRIES,
    INDIA_COUNTRY_CODES,
    INDIA_COUNTRY_WORDS,
    INDIAN_CITIES,
    INDIAN_STATES,
    UNKNOWN_LOCATION_RE,
    US_STATE_CODES,
    US_STATES,
)
from .text import normalize_space


@dataclass(frozen=True)
class GeoResult:
    status: str  # "india" | "foreign" | "unknown"
    basis: str  # "structured" | "location" | "inferred" | "none"
    evidence: str = ""

    @property
    def is_india(self) -> bool:
        return self.status == "india"


def _alternation(words: Iterable[str]) -> str:
    unique = sorted({w.strip().lower() for w in words if w.strip()}, key=len, reverse=True)
    return "|".join(re.escape(w).replace(r"\ ", r"[\s\-]+") for w in unique)


_INDIA_STRONG_RE = re.compile(
    rf"(?<![a-z0-9])(?:{_alternation(INDIA_COUNTRY_WORDS + INDIAN_STATES + INDIAN_CITIES)})(?![a-z0-9])"
)
_AMBIGUOUS_RE = re.compile(rf"(?<![a-z0-9])(?:{_alternation(AMBIGUOUS_INDIAN_CITIES)})(?![a-z0-9])")
_FOREIGN_RE = re.compile(
    rf"(?<![a-z0-9])(?:{_alternation(FOREIGN_COUNTRIES + US_STATES + ('sindh', 'balochistan', 'khyber'))})(?![a-z0-9])"
)
_IND_TOKEN_RE = re.compile(r"(?<![A-Za-z])IND(?![A-Za-z])")
_US_CODE_RE = re.compile(r"(?:^|,|\(|\s-)\s*([A-Z]{2})\s*(?=$|,|\)|\s)")
_TRAILING_IN_RE = re.compile(r",\s*in\s*$")
_UNKNOWN_RE = re.compile(UNKNOWN_LOCATION_RE, re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s*(?:;|\||/|\bor\b|\n|•|·)\s*")

_DESC_PLACES = _alternation(("india",) + INDIAN_CITIES + ("delhi", "hyderabad"))
_DESC_INDIA_RE = re.compile(
    rf"(?:\b(?:based|located|work location|job location|location|position is|role is)\b[^.\n]{{0,30}}?"
    rf"(?:\bin\b|:|-)\s*(?:the\s+)?(?:{_DESC_PLACES})(?![a-z]))"
    r"|(?:\bremote\b[\s\-(,:]*(?:\bin\s+|\bwithin\s+|\bfrom\s+)?india\b)"
    r"|(?:\bindia[- ]based\b)|(?:\bpan[- ]india\b)|(?:\banywhere in india\b)|(?:\bwithin india\b)"
)
_DESC_FOREIGN_RE = re.compile(
    r"\b(?:based in|located in|reside in|residing in|work(?:ing)? from|eligible to work in|authori[sz]ed to work in"
    r"|must (?:live|reside|be located) in)\s+(?:the\s+)?(?:united states|u\.s\.|us|usa|uk|united kingdom|canada"
    r"|europe|eu|germany|singapore|australia|philippines|mexico|brazil|poland)\b"
    r"|\bus[- ]based\b"
)


def _fold(text: str) -> str:
    return normalize_space(text).lower().replace("_", " ")


@lru_cache(maxsize=16384)
def classify_segment(segment: str) -> tuple[str, str]:
    """Return (status, evidence) for a single location segment."""
    original = normalize_space(segment)
    low = _fold(original)
    if not low or _UNKNOWN_RE.match(low):
        return "unknown", original
    strong = _INDIA_STRONG_RE.search(low)
    if strong:
        return "india", strong.group(0)
    if _IND_TOKEN_RE.search(original):
        return "india", "IND"
    foreign = _FOREIGN_RE.search(low)
    if foreign:
        return "foreign", foreign.group(0)
    for code in _US_CODE_RE.findall(original):
        if code in US_STATE_CODES:
            return "foreign", code
    ambiguous = _AMBIGUOUS_RE.search(low)
    if ambiguous:
        return "india", ambiguous.group(0)
    if _TRAILING_IN_RE.search(original):  # SmartRecruiters-style lowercase country code
        return "india", "in"
    return "unknown", original


def split_segments(text: str) -> list[str]:
    return [part for part in _SPLIT_RE.split(text or "") if part and part.strip()]


def resolve(
    location: str = "",
    country_codes: Iterable[str] = (),
    locations: Iterable[str] = (),
    description: str = "",
) -> GeoResult:
    codes = {str(code).strip().lower() for code in country_codes if code and str(code).strip()}
    if codes & INDIA_COUNTRY_CODES:
        return GeoResult("india", "structured", "country code")

    foreign_evidence = ""
    for text in [location, *locations]:
        for segment in split_segments(text):
            status, evidence = classify_segment(segment)
            if status == "india":
                return GeoResult("india", "location", evidence)
            if status == "foreign" and not foreign_evidence:
                foreign_evidence = evidence
    if codes:
        return GeoResult("foreign", "structured", ",".join(sorted(codes)))
    if foreign_evidence:
        return GeoResult("foreign", "location", foreign_evidence)

    head = _fold(description[:4000]) if description else ""
    if head:
        india = _DESC_INDIA_RE.search(head)
        foreign = _DESC_FOREIGN_RE.search(head)
        if india and not foreign:
            return GeoResult("india", "inferred", india.group(0)[:80])
        if foreign and not india:
            return GeoResult("foreign", "inferred", foreign.group(0)[:80])
    return GeoResult("unknown", "none", normalize_space(location)[:80])


def is_india_job(location: str, description: str = "") -> bool:
    """Backwards-compatible boolean wrapper."""
    return resolve(location, description=description).is_india


def location_is_unknown(location: str) -> bool:
    segments = split_segments(location)
    return not segments or all(classify_segment(segment)[0] == "unknown" for segment in segments)


def first_india_segment(texts: Iterable[str]) -> str:
    for text in texts:
        for segment in split_segments(text or ""):
            if classify_segment(segment)[0] == "india":
                return normalize_space(segment)
    return ""


def primary_india_city(texts: Iterable[str]) -> str:
    """Canonical-ish city token used for duplicate fingerprints."""
    for text in texts:
        for segment in split_segments(text or ""):
            low = _fold(segment)
            match = _INDIA_STRONG_RE.search(low) or _AMBIGUOUS_RE.search(low)
            if match and match.group(0) not in INDIA_COUNTRY_WORDS:
                return _CITY_ALIASES.get(match.group(0), match.group(0))
    return "india"


_CITY_ALIASES = {
    "bangalore": "bengaluru", "bangalore urban": "bengaluru", "bengaluru urban": "bengaluru", "blr": "bengaluru",
    "bombay": "mumbai", "gurgaon": "gurugram", "gurgoan": "gurugram", "madras": "chennai", "calcutta": "kolkata",
    "poona": "pune", "trivandrum": "thiruvananthapuram", "cochin": "kochi", "vizag": "visakhapatnam",
    "vishakhapatnam": "visakhapatnam", "bhubaneshwar": "bhubaneswar", "baroda": "vadodara", "mysore": "mysuru",
    "mangalore": "mangaluru", "new delhi": "delhi", "secunderabad": "hyderabad", "sonepat": "sonipat",
}
