"""Sanity-check a finished run's outputs.

    python scripts/check_outputs.py                       # checks outputs/ against profile.toml
    python scripts/check_outputs.py outputs_dev --profile profiles/us-software-engineer-mid.toml

Fails (exit 1) if any listed job is outside the profile's countries, an Amazon link is
not a numeric public job link, a list contains duplicate rows, the main CSV
columns changed, or a link canary failed.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jobfleet.exporters import MAIN_COLUMNS  # noqa: E402
from jobfleet.geo import resolve  # noqa: E402
from jobfleet.profile import load_profile  # noqa: E402

AMAZON_RE = re.compile(r"^https://www\.amazon\.jobs/en/jobs/\d+(?:/|$)")


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main(output_dir: Path, profile_path: Path) -> int:
    profile = load_profile(profile_path)
    targets = tuple(profile.country_codes)
    problems: list[str] = []
    names = [f.output for f in profile.families] + ([profile.adjacent.output] if profile.adjacent else []) + ["aggregator_review_today.csv"]
    lists = [output_dir / name for name in names if (output_dir / name).exists()]
    total = 0
    for path in lists:
        rows = read(path)
        total += len(rows)
        if rows and list(rows[0].keys())[: len(MAIN_COLUMNS)] != MAIN_COLUMNS:
            problems.append(f"{path.name}: unexpected columns {list(rows[0].keys())[:6]}")
        for row in rows:
            location = row.get("Location", "")
            if location and targets and resolve(location, target_codes=targets).status == "foreign":
                problems.append(f"{path.name}: location outside {', '.join(targets)}: '{location}' for {row['Company']} - {row['Exact Role Name']}")
            link = row.get("Application Link", "")
            if "amazon.jobs" in link and not AMAZON_RE.match(link):
                problems.append(f"{path.name}: malformed Amazon link {link}")
        counts = Counter((r["Company"].lower(), r["Exact Role Name"].lower(), r.get("Location", "").lower()) for r in rows)
        problems += [f"{path.name}: duplicate row {key}" for key, n in counts.items() if n > 1]
    canary = output_dir / "health" / "canary_links_latest.csv"
    if canary.exists():
        problems += [f"link canary failed: {r['Source']} {r['Reason']} {r['URL']}" for r in read(canary) if r["Status"] == "fail"]
    for problem in problems:
        print("FAIL", problem)
    print(f"Checked {total} rows in {len(lists)} files: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output_dir", type=Path, nargs="?", default=ROOT / "outputs")
    parser.add_argument("--profile", type=Path, default=ROOT / "profile.toml")
    args = parser.parse_args()
    raise SystemExit(main(args.output_dir, args.profile))
