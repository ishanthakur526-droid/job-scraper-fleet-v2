"""Cloud mode: the GitHub form must offer exactly the role library, and its values must make a valid profile."""

import re
from pathlib import Path

from jobfleet.profile import load_profile
from jobfleet.role_library import FAMILIES
from jobfleet.setup_wizard import main

ROOT = Path(__file__).resolve().parents[1]
FORM = (ROOT / ".github" / "workflows" / "setup-profile.yml").read_text(encoding="utf-8")


def _options(name: str) -> list[str]:
    block = FORM.split(f"      {name}:", 1)[1].split("\n      family_" if name != "family_3" else "\n      extra_titles:", 1)[0]
    return re.findall(r'"([^"]+)"', block.split("options:", 1)[1].split("default:", 1)[0])


def test_form_offers_every_role_family():
    names = [info["name"] for info in FAMILIES.values()]
    assert _options("family_1") == names
    assert _options("family_2") == ["(none)", *names] == _options("family_3")


def test_form_values_make_a_valid_profile(tmp_path):
    target = tmp_path / "profile.toml"
    families = "Design (UX/UI);Excel / MIS Reporting;Data & BI Analytics"
    assert main(["--yes", "--no-ai", "--countries", "United Kingdom", "--cities", "", "--remote", "include", "--years", "1",
                 "--families", families, "--titles", "", "--profile", str(target)]) == 0
    assert load_profile(target).family_ids == ["design", "excel_mis", "data_analytics"]


def test_template_copies_wait_for_their_own_profile():
    workflow = (ROOT / ".github" / "workflows" / "find-jobs.yml").read_text(encoding="utf-8")
    assert "(Ishan)" in workflow and "(Ishan)" in (ROOT / "profile.toml").read_text(encoding="utf-8")
