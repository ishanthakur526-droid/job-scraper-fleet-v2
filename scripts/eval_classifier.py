"""Measure classifier quality against a hand-labelled sample of real postings.

    python scripts/eval_classifier.py sample outputs/raw/<run>.jsonl.gz [--n 150]
        -> writes outputs/eval/to_label.csv (fill the `label` column)
    python scripts/eval_classifier.py score outputs/raw/<run>.jsonl.gz outputs/eval/labels.csv

Labels: data_bi | research | excel_mis | adjacent | none. Labelled data stays in
the gitignored outputs/ folder because it contains scraped job text.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jobfleet.classifier import Classifier  # noqa: E402
from jobfleet.pipeline import dedupe_raw  # noqa: E402
from jobfleet.profile import load_profile  # noqa: E402
from jobfleet.rawdump import read_dump  # noqa: E402

LABELS = ("data_bi", "research", "excel_mis", "adjacent", "none")


def predicted(evaluation) -> str:
    if evaluation.decision != "accept":
        return "none"
    return "adjacent" if evaluation.route == "adjacent" else evaluation.category_id


def evaluate(dump: Path):
    classifier = Classifier.from_profile(load_profile(ROOT / "profile.toml"))
    _meta, jobs, _health = read_dump(dump)
    return [classifier.evaluate(job) for job in dedupe_raw(jobs)]


def sample(args) -> None:
    evaluations = evaluate(args.dump)
    rng = random.Random(7)
    strata: dict[str, list] = defaultdict(list)
    for ev in evaluations:
        if ev.stage in ("prefilter",) or ev.reason.startswith(("excluded_entry", "outside_your_countries")):
            continue
        strata["accepted" if ev.decision == "accept" else ev.reason.split(":")[0]].append(ev)
    quota = {"accepted": int(args.n * 0.45), "possible": int(args.n * 0.15)}
    rows = []
    for name, items in sorted(strata.items()):
        rng.shuffle(items)
        take = quota.get(name, max(4, int(args.n * 0.06)))
        for ev in items[:take]:
            job = ev.job
            rows.append(
                {
                    "key": job.key(), "label": "", "predicted": predicted(ev), "reason": ev.reason, "company": job.company,
                    "title": job.title, "location": job.location, "experience": ev.experience_label,
                    "snippet": (job.requirements_text or job.description)[:300].replace("\n", " "),
                }
            )
    out = ROOT / "outputs" / "eval" / "to_label.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out} (strata: {dict(Counter(r['reason'].split(':')[0] for r in rows))})")


def score(args) -> None:
    labels = {}
    with args.labels.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("label", "").strip() in LABELS:
                labels[row["key"]] = row["label"].strip()
    preds = {ev.job.key(): (predicted(ev), ev) for ev in evaluate(args.dump)}
    pairs = [(labels[k], preds[k][0], preds[k][1]) for k in labels if k in preds]
    print(f"Labelled rows scored: {len(pairs)} (missing from dump: {len(labels) - len(pairs)})")
    for label in LABELS[:-1]:
        tp = sum(1 for gold, pred, _ in pairs if gold == label and pred == label)
        fp = sum(1 for gold, pred, _ in pairs if gold != label and pred == label)
        fn = sum(1 for gold, pred, _ in pairs if gold == label and pred != label)
        precision = tp / (tp + fp) if tp + fp else float("nan")
        recall = tp / (tp + fn) if tp + fn else float("nan")
        print(f"  {label:10} precision {precision:5.2f}  recall {recall:5.2f}  (tp {tp}, fp {fp}, fn {fn})")
    in_lists = [(g, p) for g, p, _ in pairs if p != "none"]
    if in_lists:
        print(f"  overall precision of listed jobs: {sum(g == p for g, p in in_lists) / len(in_lists):.2f}")
    print("\nMismatches:")
    for gold, pred, ev in pairs:
        if gold != pred:
            print(f"  gold={gold:9} pred={pred:9} {ev.reason[:28]:28} | {ev.job.company[:16]:16} | {ev.job.title[:60]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_sample = sub.add_parser("sample")
    p_sample.add_argument("dump", type=Path)
    p_sample.add_argument("--n", type=int, default=150)
    p_score = sub.add_parser("score")
    p_score.add_argument("dump", type=Path)
    p_score.add_argument("labels", type=Path)
    args = parser.parse_args()
    {"sample": sample, "score": score}[args.command](args)


if __name__ == "__main__":
    main()
