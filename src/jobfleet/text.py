"""Text normalisation and whole-word keyword matching."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from functools import lru_cache

from bs4 import BeautifulSoup

_PUNCT_MAP = {
    "–": "-",
    "—": "-",
    "−": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    " ": " ",
    "​": "",
    "•": " • ",
    "﻿": "",
}
_PUNCT_RE = re.compile("|".join(map(re.escape, _PUNCT_MAP)))
_BLOCK_TAGS = ("p", "li", "br", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "section", "td")


def _fix_punct(value: str) -> str:
    return _PUNCT_RE.sub(lambda m: _PUNCT_MAP[m.group(0)], value or "")


def normalize_space(value: str) -> str:
    """Collapse all whitespace into single spaces (one line)."""
    return re.sub(r"\s+", " ", _fix_punct(value)).strip()


def normalize_block(value: str) -> str:
    """Keep line structure but collapse spaces inside lines and blank lines."""
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in _fix_punct(value).split("\n"))
    return "\n".join(line for line in lines if line)


def clean_html(value: str) -> str:
    """HTML (possibly entity-escaped) -> readable text with one block per line."""
    if not value:
        return ""
    text = html.unescape(str(value))
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.find_all(_BLOCK_TAGS):
            tag.insert_before("\n")
        text = soup.get_text(" ")
    return normalize_block(text)


# ---------------------------------------------------------------- boilerplate
_BOILERPLATE_RE = re.compile(
    r"\b(?:equal (?:employment )?opportunit|affirmative action|without regard to|regardless of (?:race|age|gender|religion)"
    r"|race,? colou?r|gender identity|sexual orientation|protected (?:veteran|characteristic|status)|veteran status"
    r"|disabilit(?:y|ies)|reasonable accommodation|diversity,? equity|equity,? (?:and )?inclusion|diverse and inclusive"
    r"|inclusive (?:workplace|environment|culture)|eeo\b|e-verify|background check|privacy (?:notice|policy)"
    r"|health insurance|medical insurance|paid time off|parental leave|wellness (?:program|benefit)|401\(?k\)?"
    r"|recruitment (?:fraud|scam)|never ask (?:for|you)|fraudulent)",
    re.IGNORECASE,
)
_ABOUT_RE = re.compile(
    r"\b(?:founded in|headquartered in|our mission is|we are a (?:global|leading)|is a (?:global|leading|world)"
    r"|for more information,? visit|learn more (?:about us|at))",
    re.IGNORECASE,
)


def split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    for line in normalize_block(text).split("\n"):
        parts.extend(piece.strip() for piece in re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9(•\-])", line) if piece.strip())
    return parts


def strip_boilerplate(text: str) -> str:
    """Drop EEO / benefits / about-us sentences before keyword scoring."""
    kept = [s for s in split_sentences(text) if not _BOILERPLATE_RE.search(s) and not _ABOUT_RE.search(s)]
    return "\n".join(kept)


# ------------------------------------------------------------- keyword match
_SPECIAL_KEYWORDS = {
    # "excel" the tool, not "excel in/at" or "excellent".
    "excel": r"(?<![a-z0-9])(?:ms[- ]?|microsoft |advanced )?excel(?![a-z0-9])(?!\s+(?:in|at|as)\b)",
    "mis": r"(?<![a-z0-9])mis(?![a-z0-9])(?!-)",
    "equity": r"(?<![a-z0-9])equity(?![a-z0-9])(?!,? (?:and )?inclusion)",
    "pivot": r"(?<![a-z0-9])pivot(?:s|ing)?(?: tables?| charts?)(?![a-z0-9])",
    "research": r"(?<![a-z0-9])research(?:er|ers|ing)?(?![a-z0-9])",
}


@lru_cache(maxsize=4096)
def keyword_regex(term: str) -> re.Pattern[str]:
    term_l = term.strip().lower()
    if term_l in _SPECIAL_KEYWORDS:
        return re.compile(_SPECIAL_KEYWORDS[term_l], re.IGNORECASE)
    words = [re.escape(word) for word in term_l.split()]
    body = r"[\s\-/&]+".join(words)
    plural = r"(?:s|es)?" if re.match(r"[a-z]", term_l[-1:] or "") else ""
    return re.compile(rf"(?<![a-z0-9]){body}{plural}(?![a-z0-9])", re.IGNORECASE)


def keyword_hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term and keyword_regex(term).search(text or "")]


# --------------------------------------------------------- title normalising
_TITLE_EXPANSIONS = (
    (r"\bsr\b", "senior"),
    (r"\bjr\b", "junior"),
    (r"\bassoc\b", "associate"),
    (r"\bexec\b", "executive"),
    (r"\bmgr\b", "manager"),
    (r"\bops\b", "operations"),
    (r"\bbie\b", "business intelligence engineer"),
    (r"\bbi\b", "business intelligence"),
    (r"\bmi\b", "market intelligence"),
    (r"\bar\b", "accounts receivable"),
    (r"\bap\b", "accounts payable"),
    (r"\bp2p\b", "procure to pay"),
    (r"\bo2c\b", "order to cash"),
    (r"\br2r\b", "record to report"),
    (r"\bfpa\b", "fpa"),
)
_ROMAN_LEVELS = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
_LEVEL_DIGIT_RE = re.compile(r"\b(?:analyst|associate|engineer|specialist|executive|consultant|scientist|officer)\s+([1-5])\b")


@dataclass(frozen=True)
class NormalizedTitle:
    raw: str
    text: str
    tokens: tuple[str, ...]
    level: int | None


@lru_cache(maxsize=8192)
def normalize_title(title: str) -> NormalizedTitle:
    raw = normalize_space(title)
    t = raw.lower()
    t = re.sub(r"\bfp\s*&\s*a\b", "fpa", t)
    t = re.sub(r"\(\s*(?:contract|contractual|temporary|temp|fixed[- ]term)[^)]*\)", " ", t)
    t = re.sub(r"\b(?:req(?:uisition)?|job)\s*(?:id|no|number)?\s*[:#]?\s*[a-z]{0,3}-?\d{4,}\b", " ", t)
    t = re.sub(r"\b[a-z]{1,3}\d{5,}\b", " ", t)  # R01572558, JR368325
    t = re.sub(r"(?:^|\s)[-–|#]\s*\d{4,}\b", " ", t)  # " - 11953"
    t = re.sub(r"\b\d{5,}\b", " ", t)
    t = t.replace("&", " and ")
    t = re.sub(r"[^a-z0-9+#]+", " ", t)
    for pattern, replacement in _TITLE_EXPANSIONS:
        t = re.sub(pattern, replacement, t)
    t = re.sub(r"\s+", " ", t).strip()
    level = None
    tokens = tuple(t.split())
    for token in tokens:
        if token in _ROMAN_LEVELS:
            level = max(level or 0, _ROMAN_LEVELS[token])
    digit = _LEVEL_DIGIT_RE.search(t)
    if digit:
        level = max(level or 0, int(digit.group(1)))
    return NormalizedTitle(raw=raw, text=t, tokens=tokens, level=level)


_STOP_TOKENS = frozenset({"and", "of", "the", "for", "a", "an", "in", "to", "with"})


def phrase_in_title(norm: NormalizedTitle, phrase: str) -> bool:
    target = normalize_title(phrase).text
    return bool(target) and re.search(rf"(?<![a-z0-9]){re.escape(target)}(?![a-z0-9])", norm.text) is not None


def tokens_in_title(norm: NormalizedTitle, phrase: str, window_slack: int = 1) -> bool:
    """Order-invariant match: every role token appears close together in the title
    ('Analyst, Data' = 'Data Analyst'), ignoring stop words such as 'and'/'of'."""
    role_tokens = [tok for tok in normalize_title(phrase).tokens if tok not in _STOP_TOKENS]
    if len(role_tokens) < 2:
        return False
    title_tokens = [tok for tok in norm.tokens if tok not in _STOP_TOKENS]
    positions: list[int] = []
    for tok in role_tokens:
        if tok not in title_tokens:
            return False
        positions.append(title_tokens.index(tok))
    return max(positions) - min(positions) <= len(role_tokens) - 1 + window_slack


def truncate(text: str, limit: int) -> str:
    text = normalize_space(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
