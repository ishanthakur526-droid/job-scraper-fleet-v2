"""Replay a raw dump with a profile and compare against a saved baseline.

Used to prove that a refactor leaves results unchanged:

    # save a baseline with the current code
    python scripts/compare_runs.py outputs/raw/<run>.jsonl.gz --save outputs/baselines/before
    # ...change code...
    python scripts/compare_runs.py outputs/raw/<run>.jsonl.gz --against outputs/baselines/before

Accepted, possible, adjacent and aggregator rows must match exactly (key,
family, tier, score, experience, notes, location). Rejected jobs are compared
by decision only; changed reject reasons are summarised, not failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jobfleet.classifier import Classifier  # noqa: E402
from jobfleet.pipeline import JobPipeline  # noqa: E402
from jobfleet.profile import load_profile  # noqa: E402
from jobfleet.rawdump import read_dump  # noqa: E402

BUCKETS = ("main", "overflow", "possible", "adjacent", "aggregator")


def _row(result) -> list:
    return [result.key, result.category_id, result.quality_tier, result.score, result.experience_required, result.system_notes, result.location]


def snapshot(dump: Path, profile_path: Path) -> tuple[dict, dict]:
    classifier = Classifier.from_profile(load_profile(profile_path))
    pipeline = JobPipeline(None, classifier)  # type: ignore[arg-type]  # no network: evaluation only
    _meta, jobs, _health = read_dump(dump)
    evaluations = pipeline.evaluate(jobs)
    decisions = {
        ev.job.key(): [ev.decision, ev.route, ev.category_id, ev.tier, ev.score, ev.experience_label, ev.reason, "; ".join(ev.notes)]
        for ev in evaluations
    }
    built = pipeline.build(evaluations)
    buckets: dict = {}
    for name in BUCKETS:
        value = getattr(built, name)
        buckets[name] = {k: [_row(r) for r in rows] for k, rows in value.items()} if isinstance(value, dict) else [_row(r) for r in value]
    return decisions, buckets


def _flatten(buckets: dict) -> dict[str, tuple[str, list]]:
    rows: dict[str, tuple[str, list]] = {}
    for name, value in buckets.items():
        groups = value.items() if isinstance(value, dict) else [("", value)]
        for family, items in groups:
            for item in items:
                rows[item[0]] = (f"{name}:{family}" if family else name, item)
    return rows


def compare(before: tuple[dict, dict], after: tuple[dict, dict]) -> int:
    old_dec, old_buckets = before
    new_dec, new_buckets = after
    old_rows, new_rows = _flatten(old_buckets), _flatten(new_buckets)
    problems = 0
    for key in sorted(set(old_rows) | set(new_rows)):
        old, new = old_rows.get(key), new_rows.get(key)
        if old != new:
            problems += 1
            print(f"ROW  {key}\n  before: {old}\n  after:  {new}")
    flips = Counter()
    reasons = Counter()
    for key in sorted(set(old_dec) | set(new_dec)):
        old, new = old_dec.get(key), new_dec.get(key)
        if old is None or new is None:
            problems += 1
            print(f"KEY  {key} only {'after' if old is None else 'before'}")
            continue
        if old[0] != new[0]:
            problems += 1
            flips[(old[0], new[0])] += 1
            print(f"DEC  {key}: {old[0]} ({old[6]}) -> {new[0]} ({new[6]})")
        elif old[6] != new[6]:
            reasons[(old[6].split(":")[0], new[6].split(":")[0])] += 1
    print(f"\n{len(new_dec)} jobs, {len(new_rows)} listed rows; {problems} differences in decisions or listed rows.")
    if reasons:
        print("Reject reasons renamed (decision unchanged):")
        for (old, new), count in reasons.most_common():
            print(f"  {count:5d}  {old} -> {new}")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--profile", type=Path, default=ROOT / "profile.toml")
    parser.add_argument("--save", type=Path, help="write <prefix>_decisions.json and <prefix>_buckets.json")
    parser.add_argument("--against", type=Path, help="compare with <prefix>_decisions.json and <prefix>_buckets.json")
    args = parser.parse_args()
    decisions, buckets = snapshot(args.dump, args.profile)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        Path(f"{args.save}_decisions.json").write_text(json.dumps(decisions), encoding="utf-8")
        Path(f"{args.save}_buckets.json").write_text(json.dumps(buckets), encoding="utf-8")
        print(f"Saved {len(decisions)} decisions to {args.save}_*.json")
    if args.against:
        before = (
            json.loads(Path(f"{args.against}_decisions.json").read_text(encoding="utf-8")),
            json.loads(Path(f"{args.against}_buckets.json").read_text(encoding="utf-8")),
        )
        return compare(before, (decisions, buckets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
