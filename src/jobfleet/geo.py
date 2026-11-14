"""Where is a job? Works for any country.

A location string is split into segments (multi-location postings count if any
segment is in a target country). Each segment is scored against GeoNames data
(``data/gazetteer.json.gz``) plus hand-curated packs (``geo_data.py``):

- country names and codes ("India", "USA", trailing "IN", upper-case "IND-BLR")
- states/provinces and their codes ("Karnataka", "Austin, TX"); a code counts
  double when the city in the same segment really is in that state, so
  "San Jose, CA" is California but "Toronto, CA" is Canada
- city names weighted by population share ("Hyderabad" is 78% Indian by
  population, "Cambridge" is a toss-up between the UK and the US)

The winner must lead clearly, otherwise the segment is "unknown". Matching is
whole-word, so "Indiana" and "Indianapolis" never look like India. Only when
no location settles it are strict phrases in the description used
("based in Pune", "remote within India").
"""

from __future__ import annotations

import gzip
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Iterable

from .geo_data import (
    CITY_CANONICAL,
    COUNTRY_PACKS,
    EXTRA_PLACES,
    ISO3_ALLOWED,
    MACRO_REGIONS,
    MIDDLE_EAST,
    REMOTE_RE,
    STOP_KEYS,
    UNKNOWN_LOCATION_RE,
)
from .text import normalize_space

DEFAULT_TARGETS = frozenset({"IN"})
MIN_SCORE = 20.0
MIN_LEAD = 10.0
W_COUNTRY, W_COUNTRY_SHARED, W_ISO3, W_CODE, W_CODE_SHARED = 100.0, 50.0, 90.0, 60.0, 30.0
W_REGION, W_REGION_CODE, W_REGION_CITY_BONUS, W_CITY, W_PACK, W_PACK_WEAK = 40.0, 30.0, 30.0, 30.0, 45.0, 25.0
REGION_PRIOR_POPULATION = 20_000_000
_DIRECTIONAL = re.compile(
    r"^(?:(?:north|south|east|west|northern|southern|eastern|western|central|upper|lower|middle|greater"
    r"|capital|coast|coastal|region|province|district|islands?|northeast|northwest|southeast|southwest)\s*)+$"
)

_targets: frozenset[str] = DEFAULT_TARGETS


def set_targets(codes: Iterable[str]) -> None:
    """Countries (ISO2) that count as "target". An empty set means anywhere."""
    global _targets
    _targets = frozenset(str(c).upper() for c in codes)


def targets() -> frozenset[str]:
    return _targets


@dataclass(frozen=True)
class GeoResult:
    status: str  # "target" | "foreign" | "unknown"
    basis: str  # "structured" | "location" | "inferred" | "none"
    evidence: str = ""
    country: str = ""

    @property
    def is_target(self) -> bool:
        return self.status == "target"


# ------------------------------------------------------------------ text keys
def deaccent(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def place_key(text: str) -> str:
    """'Zürich', 'U.S.A.', 'Pimpri-Chinchwad' -> 'zurich', 'usa', 'pimpri chinchwad'."""
    t = deaccent(text or "").lower().replace(".", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def _fold(text: str) -> str:
    return deaccent(normalize_space(text)).lower().replace("_", " ")


# ------------------------------------------------------------------ gazetteer
@dataclass(frozen=True)
class Candidate:
    country: str  # ISO2, or "@<macro region>"
    kind: str  # country | region | city | pack | pack_weak | extra | macro
    population: int = 0
    admin1: str = ""


@dataclass
class Gazetteer:
    countries: dict[str, dict]
    index: dict[str, list[Candidate]] = field(default_factory=lambda: defaultdict(list))
    region_codes: dict[str, list[tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))
    iso3: dict[str, str] = field(default_factory=dict)
    iso3_any: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)  # country alias key -> ISO2
    canonical: dict[str, str] = field(default_factory=dict)  # city alias key -> canonical city key
    macros: dict[str, frozenset[str]] = field(default_factory=dict)
    big_cities: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    max_words: int = 1
    source: str = ""

    def add(self, key: str, candidate: Candidate) -> None:
        if key and candidate not in self.index[key]:
            self.index[key].append(candidate)


@lru_cache(maxsize=1)
def gazetteer() -> Gazetteer:
    raw = (resources.files("jobfleet") / "data" / "gazetteer.json.gz").read_bytes()
    data = json.loads(gzip.decompress(raw))
    gaz = Gazetteer(countries=data["countries"], source=data.get("source", ""))
    region_owners: dict[str, set[str]] = defaultdict(set)
    for iso2, names in data["regions"].items():
        for name in names:
            region_owners[place_key(name)].add(iso2)
    for iso2, info in gaz.countries.items():
        gaz.iso3_any[info["iso3"]] = iso2
        if info["iso3"] in ISO3_ALLOWED:
            gaz.iso3[info["iso3"]] = iso2
        for alias in info["aliases"]:
            key = place_key(alias)
            gaz.aliases[key] = iso2
            if len(key) > 2:  # two-letter "us"/"uk" are handled as codes
                gaz.add(key, Candidate(iso2, "country"))
    for key, owners in region_owners.items():
        if key in STOP_KEYS or len(key) < 4 or _DIRECTIONAL.match(key):
            continue  # "Central", "South East", ... exist in many countries
        for iso2 in owners:
            gaz.add(key, Candidate(iso2, "region", int(gaz.countries.get(iso2, {}).get("population", 0))))
    for word, iso2 in (("us", "US"), ("uk", "GB")):  # "Remote US", "UK - London", "U.S."
        gaz.add(word, Candidate(iso2, "code"))
    for canonical, iso2, population, admin1, alts in data["cities"]:
        canon_key = place_key(canonical)
        for name in (canonical, *alts):
            key = place_key(name)
            if key in STOP_KEYS or len(key) < 3:
                continue
            gaz.add(key, Candidate(iso2, "city", int(population), place_key(admin1)))
            gaz.canonical.setdefault(key, canon_key)
        if population >= 1_000_000:
            gaz.big_cities[iso2].append(canon_key)
    for iso2, pack in COUNTRY_PACKS.items():
        for kind, names in (("country", pack.get("country", ())), ("pack", pack.get("strong", ())), ("pack_weak", pack.get("ambiguous", ()))):
            for name in names:
                gaz.add(place_key(name), Candidate(iso2, kind))
    for name, iso2 in EXTRA_PLACES.items():
        gaz.add(place_key(name), Candidate(iso2, "extra"))
    continents: dict[str, set[str]] = defaultdict(set)
    for iso2, info in gaz.countries.items():
        continents[info["continent"]].add(iso2)
    continents["ME"] = set(MIDDLE_EAST)
    for name, members in MACRO_REGIONS.items():
        countries: set[str] = set()
        for member in members:
            countries |= continents[member[1:]] if member.startswith("@") else {member}
        gaz.macros[place_key(name)] = frozenset(countries)
        gaz.add(place_key(name), Candidate("@" + place_key(name), "macro"))
    for iso2, table in data["region_codes"].items():
        for code, name in table.items():
            gaz.region_codes[code].append((iso2, place_key(name)))
    gaz.max_words = min(6, max(len(key.split()) for key in gaz.index))
    return gaz


# ------------------------------------------------------------------ segments
_UNKNOWN_RE = re.compile(UNKNOWN_LOCATION_RE, re.IGNORECASE)
_REMOTE_RE = re.compile(REMOTE_RE, re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s*(?:;|\||/|\bor\b|\n|•|·)\s*")
_CODE_RE = re.compile(r"(?:^|,|\(|-)\s*([A-Za-z]{2,3})\s*(?=$|,|\)|\s|-)")


def _hits(key: str) -> list[tuple[str, list[Candidate]]]:
    """Longest-first, non-overlapping place names in a key ('new delhi' before 'delhi')."""
    gaz = gazetteer()
    words = key.split()
    hits: list[tuple[str, list[Candidate]]] = []
    i = 0
    while i < len(words):
        for n in range(min(gaz.max_words, len(words) - i), 0, -1):
            phrase = " ".join(words[i:i + n])
            candidates = gaz.index.get(phrase)
            if candidates:
                hits.append((phrase, candidates))
                i += n
                break
        else:
            i += 1
    return hits


@dataclass(frozen=True)
class Located:
    contenders: tuple[str, ...]  # countries within MIN_LEAD of the best score (best first)
    evidence: str
    macro: frozenset[str] = frozenset()


@lru_cache(maxsize=32768)
def locate(segment: str) -> Located:
    """Score one location segment (no target countries involved; cached)."""
    original = normalize_space(segment)
    if not original or _UNKNOWN_RE.match(_fold(original)):
        return Located((), original)
    gaz = gazetteer()
    scores: dict[str, float] = defaultdict(float)
    evidence: dict[str, str] = {}
    contributions: dict[tuple[str, str], float] = defaultdict(float)
    firm: set[str] = set()  # countries named by something other than a city ("Pakistan", "NY", "Sindh")

    def add(iso2: str, weight: float, text: str, kind: str = "") -> None:
        scores[iso2] += weight
        evidence.setdefault(iso2, text)
        contributions[(iso2, text)] += weight
        if kind in ("country", "code", "region", "pack", "iso3"):
            firm.add(iso2)

    cities: set[tuple[str, str]] = set()
    regions_named: set[tuple[str, str]] = set()
    same_word: set[tuple[str, str]] = set()
    weak: list[tuple[str, str]] = []
    macros: list[str] = []
    for key, candidates in _hits(place_key(original)):
        kinds: dict[str, list[Candidate]] = defaultdict(list)
        for candidate in candidates:
            kinds[candidate.kind].append(candidate)
        if kinds["macro"]:  # "APAC" the region, not Apac in Uganda
            macros.extend(c.country[1:] for c in kinds["macro"])
            continue
        region_owners = {c.country for c in kinds["region"]}
        for c in kinds["country"]:
            add(c.country, W_COUNTRY_SHARED if region_owners - {c.country} else W_COUNTRY, key, "country")  # "Georgia"
        for c in kinds["code"]:
            add(c.country, W_CODE, key, "code")
        weak.extend((c.country, key) for c in kinds["pack_weak"])
        if kinds["region"]:
            # A shared region name is split by country population ("Florida": the US, not Uruguay), halved when
            # the same country also has a city of that name (Kochi city and Kochi prefecture are one place), and
            # damped for small countries ("Manchester" is the English city, not the Jamaican parish).
            city_countries = {c.country for c in kinds["city"]}
            total = sum(c.population for c in kinds["region"]) or 1
            for c in kinds["region"]:
                weight = W_REGION / 2 if c.country in city_countries else W_REGION
                prior = min(1.0, c.population / REGION_PRIOR_POPULATION) if kinds["city"] else 1.0
                add(c.country, weight * prior * (c.population or 1) / total, key, "" if kinds["pack_weak"] else "region")
                regions_named.add((c.country, key))
        for c in kinds["pack"] + kinds["extra"]:
            add(c.country, W_PACK, key, "pack")
        for c in kinds["pack_weak"]:
            add(c.country, W_PACK_WEAK, key)
        if kinds["city"]:
            total = sum(c.population for c in kinds["city"]) or 1
            by_country: dict[str, int] = defaultdict(int)
            for c in kinds["city"]:
                by_country[c.country] += c.population
                cities.add((c.country, c.admin1))
                if c.admin1 == key:
                    same_word.add((c.country, key))
            for iso2, population in by_country.items():
                add(iso2, W_CITY * population / total, key)
    for iso2, region in cities & regions_named:  # "Hyderabad, Sindh" is the Pakistani Hyderabad
        if (iso2, region) not in same_word:  # but "Kochi" alone is not both Kochi city and Kochi prefecture
            add(iso2, W_REGION_CITY_BONUS, region)

    parts = [p for p in re.split(r"[,()]", original) if p.strip()]
    for match in _CODE_RE.finditer(original):
        code = match.group(1)
        upper = code.upper()
        is_last = not re.search(r"[A-Za-z]", original[match.end():])
        if len(code) == 3:
            if code.isupper() and upper in gaz.iso3:
                add(gaz.iso3[upper], W_ISO3, code, "iso3")
            elif code.isupper() and upper in gaz.region_codes:
                for iso2, region in gaz.region_codes[upper]:
                    bonus = W_REGION_CITY_BONUS if (iso2, region) in cities else 0.0
                    add(iso2, W_REGION_CODE + bonus, code, "code" if bonus or is_last else "")
            continue
        iso2 = "GB" if upper == "UK" else upper
        is_country = iso2 in gaz.countries
        if code.islower():
            if is_last and is_country and len(parts) >= 2:  # SmartRecruiters-style "Pune, in"
                add(iso2, W_CODE, code, "code")
            continue
        if not code.isupper():
            continue
        regions = gaz.region_codes.get(upper, [])
        if regions:
            for region_iso, region in regions:
                bonus = W_REGION_CITY_BONUS if (region_iso, region) in cities else 0.0
                # "Delhi, NY": a state code in the state position is firm evidence; "FL 7,8" (a floor) is not.
                firm_code = bonus or (is_last and len(regions) == 1 and not is_country)  # "IN" may be India
                add(region_iso, W_REGION_CODE / len(regions) + bonus, code, "code" if firm_code else "")
            if is_country and is_last:
                add(iso2, W_CODE if len(parts) >= 3 else W_CODE_SHARED, code, "code")  # "Pune, MH, IN" vs "Carmel, IN"
        prefix = match.start() == 0 and original[match.end():].lstrip().startswith("-")  # "US-NY-New York", "IN - HYDERABAD"
        if not regions and is_country and (is_last or prefix):
            add(iso2, W_CODE, code, "code")
        elif regions and is_country and prefix:
            add(iso2, W_CODE_SHARED, code, "code")

    # Ambiguous names ("Delhi", "Kochi", "Salem") count for their country only when nothing else in the
    # segment names a different country ("Delhi, NY", "Kochi, Japan", "Salem, OR").
    for iso2, key in weak:
        if firm - {iso2}:
            scores[iso2] -= contributions[(iso2, key)]

    if scores:
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        best = ranked[0][1]
        if best >= MIN_SCORE / 2:
            contenders = tuple(iso2 for iso2, score in ranked if best - score < MIN_LEAD)
            if best < MIN_SCORE:
                contenders += ("?",)  # weak evidence ("Cambridge"): never decides for a target country
            return Located(contenders, evidence[ranked[0][0]])
    if macros:
        return Located((), macros[0], gaz.macros[macros[0]])
    return Located((), original)


def classify_segment(segment: str, target_codes: Iterable[str] | None = None) -> tuple[str, str]:
    """(status, evidence) for one location segment: status is target | foreign | unknown."""
    wanted = _targets if target_codes is None else frozenset(target_codes)
    located = locate(segment)
    if located.contenders:
        if not wanted or (len(located.contenders) == 1 and located.contenders[0] in wanted):
            return "target", located.evidence
        if not set(located.contenders) & wanted:
            return "foreign", located.evidence
        return "unknown", located.evidence
    if located.macro and wanted and not (located.macro & wanted):
        return "foreign", located.evidence
    return "unknown", located.evidence


def segment_country(segment: str) -> str:
    located = locate(segment)
    return located.contenders[0] if len(located.contenders) == 1 else ""


def split_segments(text: str) -> list[str]:
    return [part for part in _SPLIT_RE.split(text or "") if part and part.strip()]


# ------------------------------------------------------------------ countries
@lru_cache(maxsize=1024)
def country_code(value: str) -> str:
    """'India', 'IN', 'ind', 'USA', 'United Kingdom', 'uk' -> ISO2 ('' if unknown)."""
    gaz = gazetteer()
    text = normalize_space(str(value or ""))
    upper = text.upper()
    if upper == "UK":
        return "GB"
    if len(upper) == 2 and upper in gaz.countries:
        return upper
    if len(upper) == 3 and upper in gaz.iso3_any:
        return gaz.iso3_any[upper]
    return gaz.aliases.get(place_key(text), "")


def country_name(iso2: str) -> str:
    return gazetteer().countries.get(iso2.upper(), {}).get("name", iso2)


def iso3(iso2: str) -> str:
    return gazetteer().countries.get(iso2.upper(), {}).get("iso3", iso2)


def country_names() -> list[str]:
    return sorted(info["name"] for info in gazetteer().countries.values())


# ------------------------------------------------------------------ jobs
def resolve(
    location: str = "",
    country_codes: Iterable[str] = (),
    locations: Iterable[str] = (),
    description: str = "",
    target_codes: Iterable[str] | None = None,
) -> GeoResult:
    wanted = _targets if target_codes is None else frozenset(target_codes)
    codes = {country_code(code) for code in country_codes if code and str(code).strip()} - {""}
    if codes and (not wanted or codes & wanted):
        return GeoResult("target", "structured", "country code", sorted(codes & wanted or codes)[0])

    foreign: GeoResult | None = None
    for text in [location, *locations]:
        for segment in split_segments(text):
            status, evidence = classify_segment(segment, wanted)
            if status == "target":
                return GeoResult("target", "location", evidence, segment_country(segment))
            if status == "foreign" and foreign is None:
                foreign = GeoResult("foreign", "location", evidence, segment_country(segment))
    if codes:
        return GeoResult("foreign", "structured", ",".join(sorted(c.lower() for c in codes)), sorted(codes)[0])
    if foreign:
        return foreign

    head = _fold(description[:4000]) if description else ""
    if head and wanted:
        target_re, foreign_re = _description_patterns(wanted)
        hit_target = target_re.search(head)
        hit_foreign = foreign_re.search(head) if foreign_re else None
        if hit_target and not hit_foreign:
            return GeoResult("target", "inferred", hit_target.group(0)[:80])
        if hit_foreign and not hit_target:
            return GeoResult("foreign", "inferred", hit_foreign.group(0)[:80])
    return GeoResult("unknown", "none", normalize_space(location)[:80])


_MAJOR_MARKETS = ("US", "GB", "CA", "DE", "SG", "AU", "PH", "MX", "BR", "PL", "FR", "NL", "IE", "ES", "IT", "JP", "CN", "AE", "IN", "NZ")


def _alternation(words: Iterable[str]) -> str:
    unique = sorted({w.strip().lower() for w in words if w.strip()}, key=len, reverse=True)
    return "|".join(re.escape(w).replace(r"\ ", r"[\s\-]+") for w in unique)


@lru_cache(maxsize=32)
def _description_patterns(wanted: frozenset[str]) -> tuple[re.Pattern[str], re.Pattern[str] | None]:
    gaz = gazetteer()
    names = [a for iso2 in wanted for a in gaz.countries.get(iso2, {}).get("aliases", []) if len(a) > 2]
    places = list(names)
    for iso2 in wanted:
        pack = COUNTRY_PACKS.get(iso2, {})
        places += list(pack.get("strong", ())) + [p for p in pack.get("ambiguous", ()) if p in ("delhi", "hyderabad")]
        places += gaz.big_cities.get(iso2, [])
    country = _alternation(names)
    target = re.compile(
        rf"(?:\b(?:based|located|work location|job location|location|position is|role is)\b[^.\n]{{0,30}}?"
        rf"(?:\bin\b|:|-)\s*(?:the\s+)?(?:{_alternation(places)})(?![a-z]))"
        rf"|(?:\bremote\b[\s\-(,:]*(?:\bin\s+|\bwithin\s+|\bfrom\s+)?(?:the\s+)?(?:{country})\b)"
        rf"|(?:\b(?:{country})[- ]based\b)|(?:\bpan[- ](?:{country})\b)|(?:\banywhere in (?:the\s+)?(?:{country})\b)"
        rf"|(?:\bwithin (?:the\s+)?(?:{country})\b)"
    )
    others = [a for iso2 in _MAJOR_MARKETS if iso2 not in wanted for a in gaz.countries[iso2]["aliases"] if a != "america"]
    if not wanted & gaz.macros["europe"]:
        others += ["europe", "eu"]
    short = [s for s, iso2 in (("us", "US"), ("usa", "US"), ("uk", "GB")) if iso2 not in wanted]
    foreign_parts = [
        r"\b(?:based in|located in|reside in|residing in|work(?:ing)? from|eligible to work in|authori[sz]ed to work in"
        rf"|must (?:live|reside|be located) in)\s+(?:the\s+)?(?:{_alternation(others)})\b"
    ]
    if short:
        foreign_parts.append(rf"\b(?:{'|'.join(short)})[- ]based\b")
    return target, re.compile("|".join(foreign_parts)) if others else None


def is_remote(text: str) -> bool:
    return bool(_REMOTE_RE.search(text or ""))


def location_is_unknown(location: str) -> bool:
    segments = split_segments(location)
    return not segments or all(classify_segment(segment)[0] == "unknown" for segment in segments)


def first_target_segment(texts: Iterable[str]) -> str:
    for text in texts:
        for segment in split_segments(text or ""):
            if classify_segment(segment)[0] == "target":
                return normalize_space(segment)
    return ""


def _city_id(key: str) -> str:
    canon = gazetteer().canonical.get(key, key)
    return CITY_CANONICAL.get(key, CITY_CANONICAL.get(canon, canon))


def primary_city(texts: Iterable[str]) -> str:
    """Canonical-ish city used for duplicate fingerprints ('Bangalore' == 'Bengaluru')."""
    for text in texts:
        for segment in split_segments(text or ""):
            for key, candidates in _hits(place_key(segment)):
                if any(c.kind in ("city", "pack", "pack_weak", "extra") for c in candidates) and not any(c.kind == "country" for c in candidates):
                    return _city_id(key)
    return "any"


class CityFilter:
    """Keeps jobs in the profile's cities ('Bangalore' matches 'Bengaluru'; states and areas work too)."""

    def __init__(self, cities: Iterable[str]):
        self.wanted = {_city_id(place_key(city)) for city in cities if place_key(city)}

    def __bool__(self) -> bool:
        return bool(self.wanted)

    def matches(self, texts: Iterable[str]) -> bool:
        for text in texts:
            for segment in split_segments(text or ""):
                if any(_city_id(key) in self.wanted for key, _c in _hits(place_key(segment))):
                    return True
        return False
