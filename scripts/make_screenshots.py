"""Screenshot dashboards for the README (needs `pip install playwright` and `playwright install chromium`).

    python scripts/make_screenshots.py outputs/dashboard.html docs/images/dashboard
        -> docs/images/dashboard-light.png and docs/images/dashboard-dark.png
"""

from __future__ import annotations

import sys
from pathlib import Path


def shoot(page_path: Path, prefix: Path, width: int = 1280, height: int = 860) -> list[Path]:
    from playwright.sync_api import sync_playwright

    prefix.parent.mkdir(parents=True, exist_ok=True)
    written = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("light", "dark"):
            page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=scheme, device_scale_factor=2)
            page.goto(page_path.resolve().as_uri())
            page.wait_for_timeout(300)
            out = prefix.with_name(f"{prefix.name}-{scheme}.png")
            page.screenshot(path=str(out), full_page=False)
            written.append(out)
            page.close()
        browser.close()
    return written


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    for path in shoot(Path(sys.argv[1]), Path(sys.argv[2])):
        print("wrote", path)
