"""Weekly company scout: Claude researches India-hiring companies on the web
(WebSearch/WebFetch only), deterministic verification decides what is added."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .board_discovery import verify_company_candidates
from .classifier import Classifier
from .http import HttpClient
from .llm import ClaudeRunner, clear_backoff, describe_failure, in_backoff, record_failure
from .models import Board

log = logging.getLogger(__name__)


def scout_due(state: Any, every_days: float, force: bool = False) -> bool:
    if force:
        return True
    last = state.get_meta("scout_last_success") if state else None
    if not last:
        return True
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(last) >= timedelta(days=every_days)
    except ValueError:
        return True


def build_prompt(template: str, boards: list[Board], quarantined: list[str]) -> str:
    known = sorted({board.company for board in boards if board.company})
    extra = [
        "",
        "Already monitored (do not return these unless you found a different, verifiable India careers/ATS URL):",
        ", ".join(known) or "(none)",
    ]
    if quarantined:
        extra += [
            "",
            "These monitored companies' career sources stopped working; finding their CURRENT careers/ATS URL is high value:",
            ", ".join(sorted(set(quarantined))),
        ]
    return template.rstrip() + "\n" + "\n".join(extra) + "\n"


def run_scout(
    runner: ClaudeRunner,
    config_dir: Path,
    output_dir: Path,
    state: Any,
    http: HttpClient,
    classifier: Classifier,
    boards: list[Board],
    llm_config: dict[str, Any],
    broken_companies: list[str],
    force: bool = False,
) -> str:
    cfg = llm_config.get("scout", {})
    if not cfg.get("enabled", True):
        return "disabled in config/llm.json"
    if not scout_due(state, float(cfg.get("every_days", 7)), force):
        return f"not due (last success {str(state.get_meta('scout_last_success'))[:10]}, every {cfg.get('every_days', 7)} days)"
    backoff = in_backoff(state)
    if backoff and not force:
        return f"skipped: {backoff}"
    template = (config_dir / "company_scout_prompt.md").read_text(encoding="utf-8")
    schema = json.loads((config_dir / "company_scout_schema.json").read_text(encoding="utf-8"))
    prompt = build_prompt(template, boards, broken_companies)
    log.info("Running weekly Claude company scout (this can take several minutes)...")
    result = runner.run(
        prompt,
        schema,
        tools=["WebSearch", "WebFetch"],
        timeout_s=float(cfg.get("timeout_s", 900)),
        model=cfg.get("model"),
        effort=cfg.get("effort"),
    )
    state.set_meta("scout_last_attempt", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if not result.ok:
        record_failure(state, result)
        log.warning("Company scout failed: %s", result.error)
        return f"failed - {describe_failure(result)}"
    clear_backoff(state)
    research = output_dir / "research"
    research.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    text = json.dumps(result.data, indent=2)
    (research / f"company_candidates_{stamp}.json").write_text(text, encoding="utf-8")
    (research / "company_candidates_latest.json").write_text(text, encoding="utf-8")
    verification = verify_company_candidates(config_dir, output_dir, result.data or {}, http, classifier, boards, state)
    state.set_meta("scout_last_success", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    companies = len((result.data or {}).get("companies", []))
    added = ", ".join(f"{b.company} ({b.source})" for b in verification.added) or "none"
    return f"{companies} companies proposed in {result.duration_s:.0f}s; {verification.verified} sources checked; added: {added}"
