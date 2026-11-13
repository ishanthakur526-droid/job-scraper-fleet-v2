"""Regenerate the example profiles in profiles/ from the role library.

    python scripts/make_presets.py

Each example is loaded back and validated, so a broken preset fails here.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jobfleet.profile import profile_from_dict  # noqa: E402
from jobfleet.profile_writer import Choices, render  # noqa: E402

PRESETS = {
    "us-software-engineer-mid": Choices("United States · mid-level software engineer", ["United States"], ["software_engineering"], level="mid"),
    "uk-marketing-early-career": Choices("United Kingdom · early-career marketing", ["United Kingdom"], ["marketing"], level="early_career"),
    "germany-data-scientist-senior": Choices(
        "Germany · senior data scientist", ["Germany"], ["data_science", "data_engineering"], level="senior", min_years=5, max_years=15
    ),
    "singapore-finance": Choices("Singapore · finance & accounting", ["Singapore"], ["finance_accounting"], level="early_career", max_years=4),
    "canada-customer-success": Choices("Canada · customer success", ["Canada"], ["customer_success", "sales"], level="mid", min_years=2, max_years=6),
    "remote-product-manager": Choices("Remote · product manager (US/UK/EU time zones)", ["United States", "United Kingdom", "Ireland"],
                                      ["product_management"], level="mid", remote="only"),
    "india-software-engineer-fresher": Choices("India · fresher software engineer", ["India"], ["software_engineering", "qa_testing"],
                                               level="early_career", max_years=2),
}


def main() -> int:
    import tomllib

    out = ROOT / "profiles"
    out.mkdir(exist_ok=True)
    for name, choices in PRESETS.items():
        text = render(choices)
        profile = profile_from_dict(tomllib.loads(text))  # validates
        (out / f"{name}.toml").write_text(text, encoding="utf-8")
        print(f"{name:34} {profile.describe()}")
    shutil.copyfile(ROOT / "profile.toml", out / "india-analyst-early-career.toml")  # the author's own profile
    print(f"{'india-analyst-early-career':34} (copy of profile.toml)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
