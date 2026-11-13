"""Build src/jobfleet/data/gazetteer.json.gz from GeoNames (https://www.geonames.org, CC BY 4.0).

Run once when updating the place data (needs internet, ~3.5 MB download):

    python scripts/build_gazetteer.py            # downloads into a temp folder
    python scripts/build_gazetteer.py --from DIR # or use files you already downloaded

Inputs: cities15000.zip (every city with 15,000+ people), admin1CodesASCII.txt
(states/provinces) and countryInfo.txt. The output is plain data (names,
country codes, populations), loaded by ``jobfleet.geo``.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import tempfile
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "jobfleet" / "data" / "gazetteer.json.gz"
BASE = "https://download.geonames.org/export/dump/"
FILES = ("cities15000.zip", "admin1CodesASCII.txt", "countryInfo.txt")

# Common names people write for countries, in addition to the official GeoNames name.
COUNTRY_ALIASES = {
    "US": ["united states of america", "usa", "u.s.a", "u.s.a.", "u.s.", "us", "america", "united states"],
    "GB": ["uk", "u.k.", "great britain", "britain", "england", "scotland", "wales", "northern ireland", "united kingdom"],
    "AE": ["uae", "u.a.e", "u.a.e.", "united arab emirates", "emirates"],
    "SA": ["ksa", "kingdom of saudi arabia"],
    "KR": ["korea", "republic of korea", "south korea"],
    "CZ": ["czech republic", "czechia"],
    "TR": ["turkiye", "türkiye", "turkey"],
    "VN": ["viet nam", "vietnam"],
    "NL": ["the netherlands", "holland", "netherlands"],
    "DE": ["deutschland"],
    "CN": ["prc", "mainland china", "people's republic of china"],
    "IN": ["bharat"],
    "RU": ["russian federation"],
    "CI": ["ivory coast", "cote d'ivoire"],
    "MK": ["macedonia"],
    "BA": ["bosnia", "bosnia and herzegovina"],
    "HK": ["hong kong sar", "hong kong"],
    "TW": ["taiwan"],
    "MO": ["macau", "macao"],
    "PH": ["philippines", "the philippines"],
}
# Two-letter state/province codes used in addresses ("Austin, TX", "Toronto, ON", "Pune, MH").
REGION_CODES = {
    "CA": {"AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
           "NS": "Nova Scotia", "NT": "Northwest Territories", "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island",
           "QC": "Quebec", "SK": "Saskatchewan", "YT": "Yukon"},
    "AU": {"NSW": "New South Wales", "VIC": "Victoria", "QLD": "Queensland", "WA": "Western Australia", "SA": "South Australia",
           "TAS": "Tasmania", "ACT": "Australian Capital Territory", "NT": "Northern Territory"},
    "IN": {"KA": "Karnataka", "MH": "Maharashtra", "TN": "Tamil Nadu", "TG": "Telangana", "TS": "Telangana", "AP": "Andhra Pradesh",
           "DL": "Delhi", "HR": "Haryana", "UP": "Uttar Pradesh", "WB": "West Bengal", "GJ": "Gujarat", "RJ": "Rajasthan",
           "KL": "Kerala", "MP": "Madhya Pradesh", "PB": "Punjab", "OR": "Odisha", "OD": "Odisha", "CG": "Chhattisgarh",
           "CT": "Chhattisgarh", "JH": "Jharkhand", "BR": "Bihar", "AS": "Assam", "UK": "Uttarakhand", "UT": "Uttarakhand",
           "HP": "Himachal Pradesh", "JK": "Jammu and Kashmir", "GA": "Goa", "PY": "Puducherry", "CH": "Chandigarh"},
}
# Well-known other names for big cities (GeoNames' own alternate names are mostly transliterations).
CITY_ALIASES = {
    ("Mumbai", "IN"): ["bombay"], ("Bengaluru", "IN"): ["bangalore"], ("Chennai", "IN"): ["madras"], ("Kolkata", "IN"): ["calcutta"],
    ("Pune", "IN"): ["poona"], ("Gurugram", "IN"): ["gurgaon"], ("Thiruvananthapuram", "IN"): ["trivandrum"], ("Kochi", "IN"): ["cochin"],
    ("Vadodara", "IN"): ["baroda"], ("Mysuru", "IN"): ["mysore"], ("Mangaluru", "IN"): ["mangalore"], ("Visakhapatnam", "IN"): ["vizag"],
    ("New York City", "US"): ["new york", "nyc"], ("Washington", "US"): ["washington dc", "washington d.c."],
    ("San Francisco", "US"): ["sf"], ("Frankfurt am Main", "DE"): ["frankfurt"], ("Ho Chi Minh City", "VN"): ["saigon", "ho chi minh"],
    ("Kyiv", "UA"): ["kiev"], ("Beijing", "CN"): ["peking"], ("Yangon", "MM"): ["rangoon"], ("Mexico City", "MX"): ["ciudad de mexico", "cdmx"],
    ("Munich", "DE"): ["muenchen", "munchen"], ("Koeln", "DE"): ["cologne"], ("Quebec", "CA"): ["quebec city"], ("Gothenburg", "SE"): ["goteborg"],
    ("Kuala Lumpur", "MY"): ["kl"], ("Makati City", "PH"): ["makati"], ("Taguig", "PH"): ["bgc", "bonifacio global city"],
}
_LATIN = re.compile(r"^[A-Za-z][A-Za-z .'\-]{2,40}$")


def deaccent(text: str) -> str:
    """Zürich -> Zurich (jobfleet.geo folds its input the same way, then lowercases)."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def fetch(folder: Path) -> None:
    for name in FILES:
        target = folder / name
        if not target.exists():
            print(f"Downloading {BASE}{name} ...")
            with urllib.request.urlopen(BASE + name, timeout=120) as response:  # noqa: S310 - fixed https URL
                target.write_bytes(response.read())


def read_countries(folder: Path) -> dict[str, dict]:
    countries: dict[str, dict] = {}
    for line in (folder / "countryInfo.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        iso2, iso3, name, population, continent = cols[0], cols[1], cols[4], cols[7], cols[8]
        aliases = sorted({a.lower() for a in COUNTRY_ALIASES.get(iso2, [])} | {name.lower()})
        countries[iso2] = {"name": name, "iso3": iso3, "continent": continent, "population": int(population or 0), "aliases": aliases}
    return countries


def read_admin1(folder: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for line in (folder / "admin1CodesASCII.txt").read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if len(cols) >= 3:
            names[cols[0]] = cols[2]  # "IN.19" -> "Karnataka" (ASCII name)
    return names


def read_cities(folder: Path, admin1: dict[str, str]) -> list[list]:
    with zipfile.ZipFile(folder / "cities15000.zip") as archive:
        text = io.TextIOWrapper(archive.open("cities15000.txt"), encoding="utf-8")
        rows = []
        for line in text:
            cols = line.rstrip("\n").split("\t")
            name, ascii_name, iso2, admin_code, population = cols[1], cols[2], cols[8], cols[10], int(cols[14] or 0)
            plain = deaccent(name)
            if not (_LATIN.match(ascii_name) or _LATIN.match(plain)):
                continue
            canonical = plain if _LATIN.match(plain) else ascii_name  # "Zurich", not GeoNames' ASCII "Zuerich"
            alts = {n.lower() for n in (ascii_name, plain) if _LATIN.match(n)} - {canonical.lower()}
            alts |= set(CITY_ALIASES.get((canonical, iso2), []) + CITY_ALIASES.get((ascii_name, iso2), []))
            rows.append([canonical, iso2, population, admin1.get(f"{iso2}.{admin_code}", ""), sorted(alts)])
    rows.sort(key=lambda r: -r[2])
    return rows


def build(folder: Path) -> dict:
    countries = read_countries(folder)
    admin1 = read_admin1(folder)
    regions: dict[str, list[str]] = defaultdict(list)
    for key, name in admin1.items():
        iso2 = key.split(".")[0]
        regions[iso2].append(name)
    codes = {iso2: dict(table) for iso2, table in REGION_CODES.items()}
    codes["US"] = {key.split(".")[1]: name for key, name in admin1.items() if key.startswith("US.") and len(key) == 5}
    return {
        "source": "GeoNames (https://www.geonames.org), CC BY 4.0: cities15000, admin1CodesASCII, countryInfo",
        "built": date.today().isoformat(),
        "countries": countries,
        "regions": {iso2: sorted(set(names)) for iso2, names in regions.items()},
        "region_codes": codes,
        "cities": read_cities(folder, admin1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="source", type=Path, help="folder that already holds the three GeoNames files")
    args = parser.parse_args()
    if args.source:
        data = build(args.source)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            fetch(Path(tmp))
            data = build(Path(tmp))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    OUT.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(data['countries'])} countries, {len(data['cities'])} cities, {OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
