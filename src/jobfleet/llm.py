"""Claude via the local Claude Code CLI (``claude -p``) on the user's Pro login.

No API key and no per-token billing: the CLI uses the subscription's OAuth
login. Every failure mode (CLI missing, logged out/revoked token, usage limit,
timeout, malformed output) is reported as a ``ClaudeResult`` with ``ok=False``
and never raises into the pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

AUTH_RE = re.compile(r"\b401\b|authenticat|oauth|not logged in|log ?in again|/login|invalid api key|token (?:has been )?revoked", re.I)
LIMIT_RE = re.compile(r"usage limit|rate limit|\b429\b|quota|limit (?:reached|exceeded)|too many requests|overloaded|\b529\b", re.I)
BACKOFF_HOURS = {"auth": 20, "limit": 5, "missing": 20}


@dataclass
class ClaudeResult:
    ok: bool
    data: dict[str, Any] | None = None
    error: str = ""
    kind: str = ""  # "", "disabled", "missing", "auth", "limit", "timeout", "invalid", "error", "backoff"
    duration_s: float = 0.0


def resolve_claude_exe(configured: str = "") -> str | None:
    """Explicit overrides win (an invalid override means 'missing', useful for tests)."""
    override = os.environ.get("JOBFLEET_CLAUDE_EXE", "").strip() or (configured or "").strip()
    if override:
        return override if Path(override).is_file() else None
    return shutil.which("claude")


class ClaudeRunner:
    def __init__(self, sandbox_dir: Path, configured_exe: str = "", model: str = "sonnet", effort: str = "low", isolate_settings: bool = True):
        self.sandbox_dir = sandbox_dir
        self.configured_exe = configured_exe
        self.model = model
        self.effort = effort
        self.isolate_settings = isolate_settings

    def run(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        tools: list[str] | None = None,
        timeout_s: float = 300,
        model: str | None = None,
        effort: str | None = None,
    ) -> ClaudeResult:
        if os.environ.get("JOBFLEET_DISABLE_LLM", "").strip() in ("1", "true", "yes"):
            return ClaudeResult(False, error="disabled via JOBFLEET_DISABLE_LLM", kind="disabled")
        exe = resolve_claude_exe(self.configured_exe)
        if not exe:
            return ClaudeResult(False, error="Claude Code CLI not found (install it or set JOBFLEET_CLAUDE_EXE)", kind="missing")
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        args = [
            exe, "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema, separators=(",", ":")),
            "--model", model or self.model,
            "--effort", effort or self.effort,
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--permission-mode", "dontAsk",
        ]
        if self.isolate_settings:
            args += ["--setting-sources", "project"]
        if tools:
            args += ["--tools", ",".join(tools), "--allowedTools", " ".join(tools)]
        else:
            args += ["--tools", ""]
        env = dict(os.environ, DISABLE_AUTOUPDATER="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.sandbox_dir),
                env=env,
                creationflags=creationflags,
            )
        except OSError as exc:
            return ClaudeResult(False, error=f"could not start Claude CLI: {exc}", kind="missing")
        try:
            stdout, stderr = proc.communicate(prompt.encode("utf-8"), timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            return ClaudeResult(False, error=f"timed out after {timeout_s:.0f}s", kind="timeout", duration_s=time.monotonic() - started)
        return parse_envelope(stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace"), proc.returncode, schema, time.monotonic() - started)


def parse_envelope(stdout: str, stderr: str, returncode: int, schema: dict[str, Any], duration: float = 0.0) -> ClaudeResult:
    try:
        envelope = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else None
    except (json.JSONDecodeError, IndexError):
        envelope = None
    if not isinstance(envelope, dict):
        message = (stderr or stdout or "no output").strip()[:300]
        kind = "auth" if AUTH_RE.search(message) else "limit" if LIMIT_RE.search(message) else "invalid"
        return ClaudeResult(False, error=message, kind=kind, duration_s=duration)
    text = str(envelope.get("result") or "")
    if envelope.get("is_error") or returncode != 0:
        status = str(envelope.get("api_error_status") or "")
        message = f"{status} {text}".strip()[:300] or f"exit code {returncode}"
        kind = "auth" if AUTH_RE.search(message) else "limit" if LIMIT_RE.search(message) else "error"
        return ClaudeResult(False, error=message, kind=kind, duration_s=duration)
    data = envelope.get("structured_output")
    if data is None:
        data = _json_from_text(text)
    if not isinstance(data, dict):
        return ClaudeResult(False, error="no structured output in Claude response", kind="invalid", duration_s=duration)
    problem = _validate(data, schema)
    if problem:
        return ClaudeResult(False, error=f"schema validation failed: {problem}", kind="invalid", duration_s=duration)
    return ClaudeResult(True, data=data, duration_s=duration)


def _json_from_text(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{.*\}", text or "", flags=re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _validate(data: dict[str, Any], schema: dict[str, Any]) -> str:
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - jsonschema is a declared dependency
        return ""
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        return exc.message[:200]
    return ""


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=30)
        else:
            proc.kill()
        proc.communicate(timeout=10)
    except Exception:  # pragma: no cover - best effort
        pass


# ------------------------------------------------------------- backoff state
def in_backoff(state: Any) -> str:
    until = state.get_meta("llm_backoff_until") if state else None
    if not until:
        return ""
    try:
        if datetime.fromisoformat(until) > datetime.now(timezone.utc):
            return f"{state.get_meta('llm_backoff_reason', '')} (retry after {until[:16]} UTC)"
    except ValueError:
        return ""
    return ""


def record_failure(state: Any, result: ClaudeResult) -> None:
    hours = BACKOFF_HOURS.get(result.kind)
    if state and hours:
        until = datetime.now(timezone.utc) + timedelta(hours=hours)
        state.set_meta("llm_backoff_until", until.isoformat(timespec="seconds"))
        state.set_meta("llm_backoff_reason", f"{result.kind}: {result.error[:160]}")


def clear_backoff(state: Any) -> None:
    if state and state.get_meta("llm_backoff_until"):
        state.set_meta("llm_backoff_until", "")
        state.set_meta("llm_backoff_reason", "")


def describe_failure(result: ClaudeResult) -> str:
    if result.kind == "auth":
        return "Claude CLI login is invalid or revoked - run `claude auth login` once in a terminal"
    if result.kind == "limit":
        return "Claude Pro usage limit reached - skipped, will retry on a later run"
    if result.kind == "missing":
        return "Claude Code CLI not found - Claude features skipped"
    if result.kind == "disabled":
        return "disabled for this run"
    return f"{result.kind}: {result.error[:160]}"
