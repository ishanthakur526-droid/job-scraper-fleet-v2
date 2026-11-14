"""Build the GitHub Pages site for cloud mode.

    python scripts/make_site.py SITE_DIR OUTPUT_DIR [SAMPLES_DIR]

Without example runs, SITE_DIR/index.html is your dashboard. With example runs
(the project's demo repository), index.html is a small gallery linking each dashboard.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
from pathlib import Path

DATA_RE = re.compile(r'<script type="application/json" id="data">(.*?)</script>', re.S)


def summary(page: Path) -> dict:
    match = DATA_RE.search(page.read_text(encoding="utf-8"))
    data = json.loads(match.group(1).replace("<\\/", "</")) if match else {}
    rows = [r for family in data.get("families", []) for r in family["rows"]]
    return {
        "name": data.get("profile", {}).get("name", page.parent.name),
        "describe": data.get("profile", {}).get("describe", ""),
        "jobs": len(rows),
        "new": sum(1 for r in rows if r.get("new")),
        "companies": len({r["company"] for r in rows}),
        "generated": data.get("generated", "")[:16].replace("T", " "),
    }


def gallery(cards: list[tuple[str, dict]]) -> str:
    items = "\n".join(
        f'<a class="card" href="{html.escape(href)}/"><h2>{html.escape(s["name"])}</h2><p>{html.escape(s["describe"])}</p>'
        f'<div class="stats"><span><b>{s["jobs"]}</b> jobs</span><span><b>{s["new"]}</b> new</span>'
        f'<span><b>{s["companies"]}</b> companies</span></div></a>'
        for href, s in cards
    )
    updated = max((s["generated"] for _h, s in cards), default="")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>JobFleet live demo</title><style>
:root{{--bg:#f7f7fb;--panel:#fff;--ink:#14151a;--muted:#5d6272;--line:#e4e6ee;--accent:#4f46e5}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1117;--panel:#171a22;--ink:#eceef4;--muted:#9aa1b2;--line:#272b36;--accent:#8b83ff}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:960px;margin:0 auto;padding:40px 16px}} h1{{font-size:30px;margin:0 0 8px;letter-spacing:-.02em}}
.lead{{color:var(--muted);margin:0 0 28px}} a{{color:var(--accent)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}
.card{{display:block;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;text-decoration:none;color:inherit}}
.card:hover{{border-color:var(--accent)}} .card h2{{font-size:18px;margin:0 0 6px}} .card p{{color:var(--muted);font-size:14px;margin:0 0 14px}}
.stats{{display:flex;gap:16px;font-size:14px;color:var(--muted)}} .stats b{{color:var(--ink);font-size:18px}}
footer{{margin-top:32px;color:var(--muted);font-size:14px}}
</style></head><body><div class="wrap">
<h1>JobFleet live demo</h1>
<p class="lead">Three different job searches, run by GitHub Actions on weekdays from the same open-source code. Only <code>profile.toml</code> differs.
Updated {html.escape(updated)} UTC. <a href="https://github.com/ishanthakur526-droid/jobfleet">Make your own &rarr;</a></p>
<div class="grid">{items}</div>
<footer>Jobs come from public company career sites. Place data &copy; GeoNames (CC BY 4.0).</footer>
</div></body></html>
"""


def main(site: Path, outputs: Path, samples: Path | None) -> int:
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    own = outputs / "dashboard.html"
    examples = sorted(p for p in (samples.glob("*/dashboard.html") if samples and samples.exists() else []))
    if not examples:
        shutil.copyfile(own, site / "index.html")
        cards = [(".", summary(own))]
    else:
        cards = []
        for name, page in [("india-analyst", own)] + [(p.parent.name, p) for p in examples]:
            (site / name).mkdir()
            shutil.copyfile(page, site / name / "index.html")
            cards.append((name, summary(page)))
        (site / "index.html").write_text(gallery(cards), encoding="utf-8")
    (site / ".nojekyll").write_text("", encoding="utf-8")
    lines = [f"- **{s['name']}**: {s['jobs']} jobs ({s['new']} new) at {s['companies']} companies" for _h, s in cards]
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write("### Results\n" + "\n".join(lines) + "\n\nCSV files: see the **jobfleet-results** artifact below.\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None))
