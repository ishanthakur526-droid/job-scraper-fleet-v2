"""Context-aware parser for "years of experience" requirements.

The profile gives a range, e.g. 0-3 years. A posting is kept when its required
minimum is within the range: overlapping ranges (2-5 years for a 0-3 profile)
are fine, a strict minimum above ``max_years`` (4+) rejects, and no stated
experience keeps the job. With ``min_years`` above 0, postings that top out
below it (0-2 years for a 5-10 profile) are dropped as too junior.

A number only counts when it is phrased as a candidate requirement - company
history ("over 45 years of excellence"), ages, contract lengths and implausibly
large numbers are ignored, and "preferred" qualifications never reject.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .text import normalize_block

_WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
}
_WORDNUM = "|".join(_WORD_NUMBERS)
NUM = r"(\d{1,2}(?:\.\d{1,2})?)"
UNIT = r"(years?|months?)"
MAX_CREDIBLE_YEARS = 15
DEFAULT_MAX_YEARS = 3
REVIEW_MARGIN_YEARS = 3  # "1-3 years ... 5+ years" with max 3: conflicting -> review (up to max + 3)
TOO_JUNIOR_SLACK_YEARS = 2  # open-ended "N+" counts as too junior only when N < min_years - 2

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("label", re.compile(rf"experience\s*(?:required|level|range)?\s*[:\-]\s*{NUM}\s*(?:-|to)\s*{NUM}(?!\s*\d)\s*{UNIT}?")),
    ("between", re.compile(rf"between\s+{NUM}\s*(?:and|-|to)\s*{NUM}\s*{UNIT}")),
    ("range", re.compile(rf"(?<![\d.]){NUM}\s*\+?\s*(?:-|to)\s*{NUM}\s*\+?\s*{UNIT}")),
    ("minimum", re.compile(rf"(?:a\s+minimum\s+of|minimum(?:\s+of)?|min\.?|at\s*least|atleast|no less than|not less than)\s*{NUM}\s*\+?\s*{UNIT}")),
    ("over", re.compile(rf"(?:more than|over|greater than|in excess of|upwards of)\s*{NUM}\s*\+?\s*{UNIT}")),
    ("upto", re.compile(rf"(?:up\s*to|upto|maximum(?:\s+of)?|max\.?|less than|under|below)\s*{NUM}\s*{UNIT}")),
    ("plus", re.compile(rf"(?<![\d.]){NUM}\s*(?:\+|plus)\s*{UNIT}")),
    ("ormore", re.compile(rf"(?<![\d.]){NUM}\s*{UNIT}\s*(?:or more|and above|or above|and more)")),
    ("bare", re.compile(rf"(?<![\d.\-]){NUM}\s*{UNIT}(?![a-z])")),
)
_FRESHER_RE = re.compile(
    r"\bfreshers?\b|\bno (?:prior |previous )?(?:work |professional |relevant )?experience (?:is )?(?:required|needed|necessary)\b"
    r"|\bentry[- ]level\b|\b0\s*(?:-|to)\s*\d{1,2}\s*years?\b"
)
_EXP_CUE_RE = re.compile(
    r"experience|experienced|exposure|\bwork(?:ed|ing)?\b|professional|industry|relevant|hands[- ]on|background"
    r"|track record|post[- ]qualification|\bpqe\b|employment"
    r"|\bin (?:a|an|the)?\s*(?:[a-z&/\-]+\s+){0,3}(?:role|position|field|domain|function|capacity|environment|setting|team)s?\b"
)
_CANDIDATE_CUE_RE = re.compile(
    r"\b(?:you|your|candidates?|applicants?|required|requirements?|minimum|must|should|need(?:ed)?|qualif\w*"
    r"|bachelor\w*|master\w*|degree|graduat\w*|mba|ideal|looking for|seeking)\b"
)
_COMPANY_HISTORY_RE = re.compile(
    r"\b(?:founded|established|since \d{4}|history|heritage|legacy|anniversary|in business|serving (?:clients|customers)"
    r"|trusted|helping (?:clients|customers|businesses|organi[sz]ations)|clients (?:for|across|in)|customers for"
    r"|our (?:company|firm|clients|history|founders?|team)|we(?: have|'ve| are| were)\b|(?:has|have|had)\s+(?:over\s+|more than\s+|nearly\s+|almost\s+|around\s+)?\d"
    r"|has been|have been (?:in|serving|delivering|helping)"
    r"|years of (?:history|excellence|innovation|service|trust|expertise|growth|operations|success|leadership))"
)
_AGE_RE = re.compile(r"\byears? (?:old|of age)\b|\bage (?:of|limit|between|group)\b|\baged\b")
# Internal-mobility rules ("minimum 18 months in current role") are not hiring requirements.
_INTERNAL_RE = re.compile(
    r"\b(?:current (?:role|position|grade|band|level)|internal (?:candidates?|applicants?|employees?)|time in (?:role|grade)|tenure in)\b"
)
_PREFERRED_SENTENCE_RE = re.compile(
    r"\b(?:preferred|preferably|nice[- ]to[- ]have|good[- ]to[- ]have|is a plus|would be a plus|an advantage"
    r"|added advantage|bonus|ideally|desirable|desired)\b"
)
_PREFERRED_HEADING_RE = re.compile(
    r"^(?:[-•*]\s*)?(?:preferred|desired|desirable|nice[- ]to[- ]have|good[- ]to[- ]have|bonus|plus points"
    r"|additional (?:qualifications|skills)|optional|added advantage|what would make you stand out|it would be great if)\b"
)
_BULLET_RE = re.compile(r"^[-•*·o]\s")
_KNOWN_HEADING_RE = re.compile(
    r"^(?:basic|minimum|required|preferred|desired|additional|key|core|technical|your|the|job|role)?\s*"
    r"(?:qualifications?|requirements?|responsibilities|skills(?: and experience)?|experience|education|eligibility"
    r"|what you(?:'ll| will)? (?:do|need|bring)|who you are|about (?:you|the role|the team|us)|what we offer|benefits"
    r"|nice[- ]to[- ]have|good[- ]to[- ]have|must[- ]have|job description|role overview|overview|the opportunity)\b"
)


@dataclass
class Mention:
    start: int
    end: int
    min_years: float
    max_years: float | None
    kind: str
    label: str
    sentence_index: int
    sentence: str
    preferred: bool = False


@dataclass(frozen=True)
class ExperienceResult:
    decision: str  # "accept" | "reject" | "review"
    min_years: float | None
    max_years: float | None
    label: str
    evidence: str = ""
    note: str = ""
    explicit: bool = False
    reason: str = ""  # for rejects: "experience_too_high" | "experience_too_low"

    @property
    def allowed(self) -> bool:
        return self.decision != "reject"


def _normalize(text: str) -> str:
    t = normalize_block(text).lower()
    t = re.sub(rf"\b({_WORDNUM})\s*\(\s*(\d{{1,2}})\s*\)", r"\2", t)
    t = re.sub(rf"\b({_WORDNUM})\b", lambda m: str(_WORD_NUMBERS[m.group(1)]), t)
    t = re.sub(r"\((\d{1,2}(?:\.\d)?\+?)\)", r"\1", t)
    t = re.sub(r"\byrs?\b\.?", "years", t)
    t = re.sub(r"\bexp\b\.?", "experience", t)
    return t


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _to_years(value: str, unit: str | None) -> float:
    number = float(value)
    return round(number / 12, 2) if unit and unit.startswith("month") else number


def _label(kind: str, a: str, b: str | None, unit: str | None) -> str:
    unit_word = "months" if unit and unit.startswith("month") else "years"
    if kind in ("range", "between", "label"):
        return f"{_fmt(float(a))}-{_fmt(float(b))} {unit_word}"
    if kind in ("plus", "ormore"):
        return f"{_fmt(float(a))}+ {unit_word}"
    if kind == "minimum":
        return f"minimum {_fmt(float(a))} {unit_word}"
    if kind == "over":
        return f"over {_fmt(float(a))} {unit_word}"
    if kind == "upto":
        return f"up to {_fmt(float(a))} {unit_word}"
    return f"{_fmt(float(a))} {unit_word}"


def _sentences(text: str) -> list[tuple[str, bool]]:
    """Split into sentences, tagging those inside 'preferred' sections."""
    out: list[tuple[str, bool]] = []
    preferred_mode = False
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        is_heading = not _BULLET_RE.match(stripped) and (
            (stripped.endswith(":") and len(stripped) <= 70)
            or (len(stripped) <= 50 and _KNOWN_HEADING_RE.match(stripped) is not None and not re.search(r"\d", stripped))
        )
        if is_heading:
            preferred_mode = bool(_PREFERRED_HEADING_RE.match(stripped))
            if not re.search(r"\d", stripped):
                continue
        for piece in re.split(r"(?<=[.;!?])\s+", stripped):
            if piece.strip():
                out.append((piece.strip(), preferred_mode))
    return out


def _extract(sentence: str, index: int, section_preferred: bool, cap: float = MAX_CREDIBLE_YEARS) -> list[Mention]:
    taken: list[tuple[int, int]] = []
    mentions: list[Mention] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(sentence):
            start, end = match.span()
            if any(start < t_end and end > t_start for t_start, t_end in taken):
                continue
            groups = match.groups()
            if kind in ("range", "between", "label"):
                a, b, unit = groups[0], groups[1], groups[2]
                low, high = _to_years(a, unit), _to_years(b, unit)
                if low > high:
                    continue
                min_y, max_y = low, high
            elif kind == "upto":
                a, unit = groups[0], groups[1]
                min_y, max_y, b = 0.0, _to_years(a, unit), None
            else:
                a, unit = groups[0], groups[1]
                min_y = _to_years(a, unit)
                if kind == "over" and not (unit or "").startswith("month"):
                    min_y = float(int(min_y) + 1)
                max_y, b = None, None
            if not _credible(sentence, start, end, kind, max(min_y, max_y or 0), cap):
                continue
            taken.append((start, end))
            mentions.append(
                Mention(
                    start=start,
                    end=end,
                    min_years=min_y,
                    max_years=max_y,
                    kind=kind,
                    label=_label(kind, a, b, unit),
                    sentence_index=index,
                    sentence=sentence,
                    preferred=section_preferred or bool(_PREFERRED_SENTENCE_RE.search(sentence)),
                )
            )
    mentions.sort(key=lambda m: m.start)
    return mentions


def _credible(sentence: str, start: int, end: int, kind: str, magnitude: float, cap: float = MAX_CREDIBLE_YEARS) -> bool:
    if magnitude > cap:
        return False
    if _AGE_RE.search(sentence) or _INTERNAL_RE.search(sentence):
        return False
    candidate = _CANDIDATE_CUE_RE.search(sentence) is not None
    if _COMPANY_HISTORY_RE.search(sentence) and not candidate:
        return False
    if kind == "label":
        return True
    window = sentence[max(0, start - 60): end + 60]
    exp_cue = _EXP_CUE_RE.search(window) is not None
    if kind == "bare":
        return exp_cue
    return exp_cue or candidate


def _collapse_alternatives(mentions: list[Mention]) -> list[Mention]:
    """'5+ years, or 3+ years with a Master's' -> keep the easier alternative."""
    if len(mentions) < 2:
        return mentions
    groups: list[list[Mention]] = [[mentions[0]]]
    for previous, current in zip(mentions, mentions[1:], strict=False):
        between = current.sentence[previous.end:current.start]
        if current.sentence_index == previous.sentence_index and re.search(r"\bor\b", between):
            groups[-1].append(current)
        else:
            groups.append([current])
    return [min(group, key=lambda m: m.min_years) for group in groups]


def _title_mentions(title: str, cap: float = MAX_CREDIBLE_YEARS) -> list[Mention]:
    """Experience stated in the title ('MI / 6 to 12 Years /', 'Exp- 4-6 yrs') is a requirement."""
    text = _normalize(title or "")
    for kind, pattern in _PATTERNS:
        if kind in ("bare", "upto"):
            continue
        for match in pattern.finditer(text):
            groups = match.groups()
            if kind in ("range", "between", "label"):
                low, high = _to_years(groups[0], groups[2]), _to_years(groups[1], groups[2])
                if low <= high <= cap:
                    label = _label(kind, groups[0], groups[1], groups[2])
                    return [Mention(match.start(), match.end(), low, high, kind, label, -1, title)]
            else:
                years = _to_years(groups[0], groups[1])
                if years <= cap:
                    label = _label(kind, groups[0], None, groups[1])
                    return [Mention(match.start(), match.end(), years, None, kind, label, -1, title)]
    return []


def credible_cap(max_years: float) -> float:
    """Largest believable requirement: 15 years, more for senior profiles (a 10-30 year search reads "20+ years")."""
    return max(float(MAX_CREDIBLE_YEARS), min(40.0, max_years + 5))


def parse_experience(
    text: str,
    preferred_text: str = "",
    title: str = "",
    *,
    min_years: float = 0,
    max_years: float = DEFAULT_MAX_YEARS,
) -> ExperienceResult:
    """Parse required experience against the profile's range; ``preferred_text`` never rejects."""
    cap = credible_cap(max_years)
    body = _normalize(text or "")
    title_mentions = _title_mentions(title, cap)
    if not body.strip() and not (preferred_text or "").strip() and not title_mentions:
        return ExperienceResult("accept", None, None, "Unspecified", note="No description text available")

    mentions: list[Mention] = list(title_mentions)
    for index, (sentence, preferred) in enumerate(_sentences(body)):
        mentions.extend(_extract(sentence, index, preferred, cap))
    pref_body = _normalize(preferred_text or "")
    for index, (sentence, _preferred) in enumerate(_sentences(pref_body), start=10_000):
        for mention in _extract(sentence, index, True, cap):
            mention.preferred = True
            mentions.append(mention)

    required = _collapse_alternatives([m for m in mentions if not m.preferred])
    preferred = [m for m in mentions if m.preferred]

    if required:
        binding = max(required, key=lambda m: m.min_years)
        floor = min(required, key=lambda m: m.min_years)
        evidence = _evidence(binding)
        if binding.min_years <= max_years:
            if min_years > 0 and _too_junior(binding, min_years):
                return ExperienceResult(
                    "reject",
                    binding.min_years,
                    binding.max_years,
                    binding.label,
                    evidence,
                    note=f"Rejected: posting asks for {binding.label}, below your minimum of {_fmt(min_years)} years",
                    explicit=True,
                    reason="experience_too_low",
                )
            return ExperienceResult("accept", binding.min_years, binding.max_years, binding.label, evidence, explicit=True)
        if floor.min_years <= max_years and binding.min_years <= max_years + REVIEW_MARGIN_YEARS:
            return ExperienceResult(
                "review",
                floor.min_years,
                binding.max_years,
                f"{floor.label} / {binding.label}",
                evidence,
                note="Conflicting experience requirements; verify before applying",
                explicit=True,
            )
        return ExperienceResult(
            "reject",
            binding.min_years,
            binding.max_years,
            binding.label,
            evidence,
            note=f"Rejected: required minimum is {binding.label}",
            explicit=True,
            reason="experience_too_high",
        )
    if preferred:
        easiest = min(preferred, key=lambda m: m.min_years)
        return ExperienceResult(
            "accept", None, None, f"Preferred: {easiest.label}", _evidence(easiest), note="Only preferred experience stated"
        )
    if _FRESHER_RE.search(body):
        if min_years > TOO_JUNIOR_SLACK_YEARS:
            return ExperienceResult(
                "reject", 0.0, None, "Fresher / 0 years", note="Rejected: entry-level posting", explicit=True, reason="experience_too_low"
            )
        return ExperienceResult("accept", 0.0, None, "Fresher / 0 years", explicit=True)
    return ExperienceResult("accept", None, None, "Unspecified")


def _too_junior(mention: Mention, min_years: float) -> bool:
    if mention.max_years is not None:
        return mention.max_years < min_years
    return mention.min_years < min_years - TOO_JUNIOR_SLACK_YEARS


def _evidence(mention: Mention) -> str:
    sentence = mention.sentence
    start = max(0, mention.start - 50)
    snippet = sentence[start: mention.end + 70].strip()
    return snippet if len(snippet) <= 160 else snippet[:159] + "…"
