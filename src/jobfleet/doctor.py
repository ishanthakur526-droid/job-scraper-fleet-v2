"""`jobfleet doctor`: plain-language checks of everything a run needs."""

from __future__ import annotations

import importlib
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"


def run_checks(root: Path, network: bool = True) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []

    def add(status: str, what: str, detail: str = "") -> None:
        checks.append((status, what, detail))

    version = sys.version_info
    add(OK if version >= (3, 11) else FAIL, f"Python {version.major}.{version.minor}", "" if version >= (3, 11) else "JobFleet needs Python 3.11 or newer")
    for module in ("curl_cffi", "bs4", "jsonschema"):
        try:
            importlib.import_module(module)
            add(OK, f"Library {module}")
        except ImportError:
            add(FAIL, f"Library {module}", "missing - run Setup.bat again (or `uv sync`)")

    from .config import load_boards
    from .profile import ProfileError, load_profile

    profile = None
    try:
        profile = load_profile(root / "profile.toml")
        add(OK, "profile.toml", profile.describe())
    except ProfileError as exc:
        add(FAIL, "profile.toml", str(exc).replace("\n", " "))
    try:
        boards, _ = load_boards(root / "config")
        add(OK, "Company list", f"{len(boards)} companies (config/companies.json + my_companies.txt)")
    except (OSError, ValueError) as exc:
        add(FAIL, "Company list", str(exc))

    try:
        outputs = root / "outputs"
        outputs.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=outputs, delete=True):
            pass
        add(OK, "Output folder", str(outputs))
    except OSError as exc:
        add(FAIL, "Output folder", f"cannot write: {exc}")

    if network:
        from .http import FetchError, HttpClient

        try:
            HttpClient().get_json("https://boards-api.greenhouse.io/v1/boards/gitlab/jobs?content=false")
            add(OK, "Internet", "job boards reachable")
        except (FetchError, ValueError) as exc:
            add(FAIL, "Internet", f"could not reach a job board: {exc}")

    from .llm import resolve_claude_exe

    claude = resolve_claude_exe(str((profile.ai if profile else {}).get("claude_exe") or ""))
    if not (profile and profile.ai.get("enabled", True)):
        add(OK, "Claude", "turned off in profile.toml (optional)")
    elif not claude:
        add(WARN, "Claude", "not installed - optional; see https://claude.com/claude-code (JobFleet works without it)")
    else:
        try:
            out = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=30)
            add(OK if out.returncode == 0 else WARN, "Claude Code CLI", (out.stdout or out.stderr).strip()[:80])
        except (OSError, subprocess.TimeoutExpired) as exc:
            add(WARN, "Claude Code CLI", str(exc))

    if platform.system() == "Windows":
        try:
            out = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=30)
            names = [line.split(",")[0].strip('"\\') for line in out.stdout.splitlines()]
            mine = [n for n in names if "jobfleet" in n.lower() or "job scraper fleet" in n.lower()]
            add(OK if mine else WARN, "Daily schedule", ", ".join(mine) if mine else "not scheduled - run `jobfleet schedule` to run it every day")
        except (OSError, subprocess.TimeoutExpired):
            add(WARN, "Daily schedule", "could not read Task Scheduler")
    return checks


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    root = Path(os.environ.get("JOBFLEET_HOME") or Path.cwd())
    print(f"JobFleet doctor - checking {root}\n")
    checks = run_checks(root, network="--offline" not in (argv or []))
    for status, what, detail in checks:
        print(f"  [{status}] {what}" + (f": {detail}" if detail else ""))
    failed = [c for c in checks if c[0] == FAIL]
    print("\nAll good - you are ready to run JobFleet." if not failed else f"\n{len(failed)} problem(s) to fix (see FAIL lines above).")
    return 1 if failed else 0
