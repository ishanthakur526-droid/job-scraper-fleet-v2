"""`jobfleet setup`: answer a few questions, get a working profile.toml.

Three ways in:
- interactive (Setup.bat / `jobfleet setup`): about six plain-language questions
- flags (`jobfleet setup --countries India --years 2 --families data_analytics`), used by the GitHub form
- `--describe "frontend developer in Berlin, 4 years"`: Claude fills in the answers (optional)
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Callable

from .geo import country_code, country_name, country_names
from .profile import ProfileError, closest, profile_from_dict
from .profile_writer import Choices, render
from .role_library import FAMILIES, find

Ask = Callable[[str], str]


def level_for_years(years: float, student: bool = False) -> tuple[str, float, float]:
    """Seniority preset and the experience range to search for someone with ``years`` of experience."""
    if student:
        return "student", 0, 1
    if years < 1:
        return "early_career", 0, 2
    if years < 3:
        return "early_career", 0, round(years + 2)
    if years < 7:
        return "mid", max(1, round(years - 2)), round(years + 3)
    if years < 12:
        return "senior", round(years - 3), round(years + 5)
    return "leadership", round(years - 4), 30


def parse_countries(text: str) -> tuple[list[str], list[str]]:
    """'India, usa' -> (['India', 'United States'], []); unknown names come back in the second list with a hint."""
    names, problems = [], []
    for raw in [part.strip() for part in re.split(r"[,;/]", text) if part.strip()]:
        code = country_code(raw)
        if code:
            names.append(country_name(code))
        else:
            guess = closest(raw, country_names() + ["USA", "UK", "UAE"])
            problems.append(f"'{raw}' is not a country I know" + (f" - did you mean {guess}?" if guess else "."))
    return list(dict.fromkeys(names)), problems


def parse_families(text: str) -> tuple[list[str], list[str]]:
    ids, problems = [], []
    keys = list(FAMILIES)
    for raw in [part.strip() for part in re.split(r"[,;]", text) if part.strip()]:
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            ids.append(keys[int(raw) - 1])
        elif find(raw):
            ids.append(find(raw))
        else:
            problems.append(f"'{raw}' is not one of the role families")
    return list(dict.fromkeys(ids)), problems


def _split(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;]", text or "") if part.strip()]


# ----------------------------------------------------------------- interactive
def interview(ask: Ask = input, say: Callable[[str], None] = print, claude_available: bool = False) -> Choices:
    say("\nLet's set up your job search. Press Enter to accept the suggestion in [brackets].\n")

    while True:
        countries, problems = parse_countries(ask("1/6  Which country or countries do you want to work in? [India]: ") or "India")
        if countries and not problems:
            break
        say("     " + "; ".join(problems or ["Please enter at least one country."]))

    cities = _split(ask("2/6  Only certain cities? Type them separated by commas, or press Enter for the whole country: "))

    remote_answer = ask("3/6  Remote jobs? 1 = include them too, 2 = remote only, 3 = no remote [1]: ").strip() or "1"
    remote = {"1": "include", "2": "only", "3": "exclude"}.get(remote_answer, "include")

    while True:
        years_text = ask("4/6  How many years of work experience do you have? [0]: ").strip() or "0"
        try:
            years = float(years_text)
            break
        except ValueError:
            say("     Please type a number, e.g. 0, 2 or 5.5")
    student = years < 1 and ask("     Are you a student looking for internships? (y/N): ").strip().lower().startswith("y")
    level, low, high = level_for_years(years, student)
    custom = ask(f"     I'll look for jobs asking {low:g}-{high:g} years. Enter to accept, or type a range like 2-5: ").strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", custom)
    if match and float(match.group(1)) <= float(match.group(2)):
        low, high = float(match.group(1)), float(match.group(2))

    say("\n5/6  Which kinds of jobs? Pick one or more numbers, separated by commas:")
    for index, info in enumerate(FAMILIES.values(), start=1):
        say(f"     {index:2}. {info['name']:<32} e.g. {', '.join(info['titles'][:3])}")
    while True:
        families, problems = parse_families(ask("     Your choice(s) [5]: ") or "5")
        if families and not problems:
            break
        say("     " + "; ".join(problems or ["Pick at least one number from the list."]))

    extra = _split(ask("6/6  Any other job titles to include? (comma-separated, Enter to skip): "))
    ai = False
    if claude_available:
        ai = not ask("     Claude Code is installed: use it for weekly company scouting and a daily second opinion? (Y/n): ").strip().lower().startswith("n")

    first = FAMILIES[families[0]]["name"]
    where = ", ".join(cities or countries) if (cities or countries) else "Remote"
    return Choices(
        name=f"{where} · {first}" + (" +" if len(families) > 1 else ""),
        countries=countries,
        cities=cities,
        remote=remote,
        level=level,
        min_years=low,
        max_years=high,
        families=families,
        extra_titles=extra,
        ai=ai,
    )


# ----------------------------------------------------------------- describe (Claude)
DESCRIBE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["countries", "cities", "remote", "years", "families", "extra_titles"],
    "properties": {
        "countries": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "cities": {"type": "array", "items": {"type": "string"}},
        "remote": {"type": "string", "enum": ["include", "only", "exclude"]},
        "years": {"type": "number", "minimum": 0, "maximum": 40},
        "families": {"type": "array", "items": {"type": "string", "enum": list(FAMILIES)}, "minItems": 1, "maxItems": 4},
        "extra_titles": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
    },
}


def describe_with_claude(description: str, runner) -> Choices:
    catalogue = "\n".join(f"- {fid}: {info['name']} ({', '.join(info['titles'][:5])})" for fid, info in FAMILIES.items())
    prompt = (
        "Turn this job-search wish into settings. Use English country names. 'years' is the person's experience. "
        "Pick 1-3 role families from the list; put specific titles that the families lack into extra_titles. "
        "remote: 'only' if they want remote work only, 'exclude' if they refuse remote, else 'include'.\n\n"
        f"Role families:\n{catalogue}\n\nWish (from the user): {description}"
    )
    result = runner.run(prompt, DESCRIBE_SCHEMA, tools=None, timeout_s=180)
    if not result.ok:
        raise ProfileError(f"Claude could not read the description ({result.error}). Run `jobfleet setup` without --describe instead.")
    data = result.data or {}
    countries, problems = parse_countries(", ".join(data.get("countries", [])))
    if problems or not countries:
        raise ProfileError("Claude suggested countries I could not recognise: " + "; ".join(problems))
    level, low, high = level_for_years(float(data.get("years", 0)))
    return Choices(
        name=description[:60],
        countries=countries,
        cities=list(data.get("cities") or []),
        remote=str(data.get("remote") or "include"),
        level=level,
        min_years=low,
        max_years=high,
        families=list(data["families"]),
        extra_titles=list(data.get("extra_titles") or []),
    )


# ----------------------------------------------------------------- entry point
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobfleet setup", description="Create profile.toml by answering a few questions.")
    parser.add_argument("--profile", type=Path, default=Path("profile.toml"), help="where to write (default: profile.toml)")
    parser.add_argument("--describe", help="describe the job you want in one sentence; Claude fills in the rest")
    parser.add_argument("--countries", help="non-interactive: e.g. 'India' or 'United States, Canada'")
    parser.add_argument("--cities", default="", help="optional, comma-separated")
    parser.add_argument("--remote", choices=["include", "only", "exclude"], default="include")
    parser.add_argument("--years", type=float, default=0, help="your years of experience")
    parser.add_argument("--student", action="store_true", help="looking for internships")
    parser.add_argument("--min-years", type=float)
    parser.add_argument("--max-years", type=float)
    parser.add_argument("--families", help="role families by name, id or number, comma-separated")
    parser.add_argument("--titles", default="", help="extra job titles, comma-separated")
    parser.add_argument("--custom-family", default="", help="put --titles into a new family with this name")
    parser.add_argument("--name", default="")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--yes", action="store_true", help="overwrite an existing profile without asking")
    return parser


def main(argv: list[str] | None = None, ask: Ask = input) -> int:
    args = build_parser().parse_args(argv)
    from .llm import ClaudeRunner, resolve_claude_exe

    claude = resolve_claude_exe()
    try:
        if args.countries or args.families:
            choices = _from_flags(args)
        elif args.describe:
            if not claude:
                raise ProfileError("--describe needs the Claude Code CLI (https://claude.com/claude-code). Run `jobfleet setup` instead.")
            choices = describe_with_claude(args.describe, ClaudeRunner(args.profile.resolve().parent / "outputs" / "llm_sandbox"))
            choices.ai = not args.no_ai
        else:
            choices = interview(ask, claude_available=bool(claude))
        text = render(choices)
        profile = profile_from_dict(tomllib.loads(text))
    except ProfileError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled; nothing was changed.", file=sys.stderr)
        return 1

    target = args.profile
    if target.exists():
        if not args.yes and not ask(f"\n{target} already exists. Replace it? A backup is kept. (y/N): ").strip().lower().startswith("y"):
            print("Nothing was changed.")
            return 1
        backup = target.with_name(target.stem + ".backup.toml")
        shutil.copyfile(target, backup)
        print(f"Saved the old profile as {backup.name}")
    target.write_text(text, encoding="utf-8")
    print(f"\nSaved {target}: {profile.describe()}")
    print("Next: double-click Run.bat (or run `jobfleet run`). Edit profile.toml any time to fine-tune.")
    return 0


def _from_flags(args: argparse.Namespace) -> Choices:
    countries, problems = parse_countries(args.countries or "")
    families, family_problems = parse_families(args.families or "")
    titles = _split(args.titles)
    if not families:
        family_problems.append("choose at least one role family with --families (--custom-family adds titles next to it)")
    country_problems = bool(problems)
    problems += family_problems
    if not countries and args.remote != "only" and not country_problems:
        problems.append("choose at least one country with --countries (or --remote only)")
    if problems:
        raise ProfileError("Setup needs a fix:\n- " + "\n- ".join(problems))
    level, low, high = level_for_years(args.years, args.student)
    return Choices(
        name=args.name or f"{', '.join(countries) or 'Remote'} · {FAMILIES[families[0]]['name']}",
        countries=countries,
        cities=_split(args.cities),
        remote=args.remote,
        level=level,
        min_years=args.min_years if args.min_years is not None else low,
        max_years=args.max_years if args.max_years is not None else high,
        families=families,
        extra_titles=titles,
        custom_family=args.custom_family,
        ai=not args.no_ai,
    )
