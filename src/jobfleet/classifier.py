"""Job classification: title gate -> geo -> experience -> role-family scoring.

Every rule comes from the search profile (``profile.toml``): which seniority
levels are allowed, conditional or excluded (``levels.py``), which job domains
are off-limits, the role families and their titles, and the experience range.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

from .experience import DEFAULT_MAX_YEARS, ExperienceResult, parse_experience
from .geo import GeoResult, resolve
from .levels import DOMAINS, LEVEL_3_PLUS, LEVELS
from .models import Category, RawJob
from .profile import Rules, default_rules
from .text import NormalizedTitle, keyword_hits, normalize_title, phrase_in_title, set_title_abbreviations, strip_boilerplate, tokens_in_title

if TYPE_CHECKING:
    from .profile import Profile

ACCEPT_THRESHOLD = 55
HIGH_CONFIDENCE_THRESHOLD = 75
POSSIBLE_THRESHOLD = 30
DEFAULT_ROLE_WEIGHT = 60
TOKEN_MATCH_PENALTY = 10
TITLE_KEYWORD_WEIGHT = 35
CONDITIONAL_TITLE_KEYWORD_WEIGHT = 50
EVIDENCE_POINTS = 5
EVIDENCE_CAP = 25

ENTRY_LEVELS = ("intern", "entry_program")
_LEVEL_NAMES = tuple(LEVELS)
_AFTER_SENIOR = _LEVEL_NAMES[_LEVEL_NAMES.index("senior") + 1:]
_FLAG_LEVELS = {"director": "director", "vp": "vp", "executive": "chief", "c_level": "chief"}


@dataclass(frozen=True)
class TitleGate:
    status: str  # "ok" | "conditional" | "reject"
    reason: str
    norm: NormalizedTitle


@dataclass(frozen=True)
class Role:
    raw: str
    weight: int
    requires_title_keyword: bool = False


@dataclass
class CategoryScore:
    category: Category
    score: int
    title_score: int
    matched: list[str]
    disqualified: str = ""


@dataclass
class Evaluation:
    job: RawJob
    decision: str  # "accept" | "possible" | "reject"
    route: str = "main"
    category_id: str = ""
    score: int = 0
    tier: str = ""
    reason: str = ""
    stage: str = ""
    geo: GeoResult | None = None
    experience: ExperienceResult | None = None
    matched_terms: list[str] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    also_matched: list[str] = field(default_factory=list)

    @property
    def experience_label(self) -> str:
        return self.experience.label if self.experience else ""


Span = tuple[int, int]


class Classifier:
    def __init__(
        self,
        categories: list[Category],
        adjacent: Category | None = None,
        *,
        rules: Rules | None = None,
        min_years: float = 0,
        max_years: float = DEFAULT_MAX_YEARS,
    ):
        self.categories = [c for c in categories if c.route == "main"]
        self.adjacent = adjacent
        self.rules = rules or default_rules(self.all_categories)
        self.min_years = float(min_years)
        self.max_years = float(max_years)
        set_title_abbreviations(self.rules.abbreviations)
        self._roles = {c.id: _roles(c) for c in self.all_categories}
        self._domains = [DOMAINS[name] for name in DOMAINS if name in set(self.rules.excluded_domains)]
        senior_words = "|".join(re.escape(w) for w in self.rules.senior_only_for)
        self._senior_only = re.compile(rf"\bsenior\s+(?:[a-z]+\s+){{0,3}}?(?:{senior_words})\b") if senior_words else None

    @classmethod
    def from_profile(cls, profile: Profile) -> Classifier:
        return cls(profile.families, profile.adjacent, rules=profile.rules, min_years=profile.min_years, max_years=profile.max_years)

    @property
    def all_categories(self) -> list[Category]:
        return self.categories + ([self.adjacent] if self.adjacent else [])

    # ------------------------------------------------------------ title gate
    def title_gate(self, title: str, flags: dict | None = None) -> TitleGate:
        flags = flags or {}
        norm = normalize_title(title)
        actions = self.rules.level_actions
        if flags.get("intern") or flags.get("university"):
            level = "intern" if flags.get("intern") else "entry_program"
            if actions.get(level) == "exclude":
                return TitleGate("reject", "excluded_entry_title:" + ("intern" if flags.get("intern") else "university"), norm)
        level_flag = str(flags.get("experience_level") or "").lower()
        if level_flag in {"internship", "intern"} and actions.get("intern") == "exclude":
            return TitleGate("reject", "excluded_entry_title:internship", norm)
        if level_flag in _FLAG_LEVELS and actions.get(_FLAG_LEVELS[level_flag]) == "exclude":
            return TitleGate("reject", f"excluded_seniority:{level_flag}", norm)
        if flags.get("people_manager") and actions.get("manager") == "exclude":
            return TitleGate("reject", "excluded_seniority:people_manager", norm)

        spans = self._target_spans(norm)
        text = norm.text
        # Entry-level words are reported by the leftmost hit ("Trainee Intern" -> trainee).
        entry = [m for name in ENTRY_LEVELS if actions.get(name) == "exclude" for m in _hits(LEVELS[name].pattern, text, spans)]
        if entry:
            return TitleGate("reject", f"excluded_entry_title:{min(entry, key=lambda m: m.start()).group(0)}", norm)

        conditional: list[str] = []
        working = text
        for name, level in LEVELS.items():
            action = actions.get(name, "allow")
            if name in ENTRY_LEVELS and action == "exclude":
                continue
            hits = _hits(level.pattern, working, spans)
            if not hits:
                continue
            if name == "senior" and action != "exclude" and self._senior_only is not None:
                # "Senior" is only acceptable in the listed titles (Senior Analyst) and never with Lead/Manager etc.
                blocked = any(actions.get(n) == "exclude" and _hits(LEVELS[n].pattern, working, spans) for n in _AFTER_SENIOR)
                if blocked or not self._senior_only.search(working):
                    return TitleGate("reject", "excluded_seniority:senior", norm)
            if action == "exclude":
                prefix = "excluded_entry_title" if name in ENTRY_LEVELS else "excluded_seniority"
                detail = hits[0].group(0) if name in ENTRY_LEVELS else level.label
                return TitleGate("reject", f"{prefix}:{detail}", norm)
            if action == "conditional":
                conditional.append(f"{name}_title")
            working = _blank(working, hits)  # so "Assistant Manager" does not also trip "manager"
        if norm.level and norm.level >= 3:
            action = actions.get(LEVEL_3_PLUS, "allow")
            if action == "exclude":
                return TitleGate("reject", f"excluded_seniority:level_{norm.level}", norm)
            if action == "conditional":
                conditional.append(f"level_{norm.level}_title")
        if conditional:
            return TitleGate("conditional", "+".join(conditional), norm)
        return TitleGate("ok", "", norm)

    def non_target(self, norm: NormalizedTitle) -> str:
        spans: list[Span] | None = None
        for domain in self._domains:
            if not domain.pattern.search(norm.text):
                continue
            if domain.exception and domain.exception.search(norm.text):
                continue
            spans = self._target_spans(norm) if spans is None else spans
            if _hits(domain.pattern, norm.text, spans):
                return domain.name
        return ""

    def _target_spans(self, norm: NormalizedTitle) -> list[Span]:
        """Where the title contains one of the profile's own job titles. Level and domain words inside such a
        span are part of the wanted title ("Product Manager", "BI Engineer") and are not held against it."""
        spans: list[Span] = []
        for category in self.all_categories:
            has_keyword: bool | None = None
            for role in self._roles[category.id]:
                if role.requires_title_keyword:
                    if has_keyword is None:
                        has_keyword = bool(category.title_keywords) and bool(keyword_hits(norm.text, category.title_keywords))
                    if not has_keyword:
                        continue
                target = normalize_title(role.raw).text
                if target:
                    spans.extend(m.span() for m in _phrase_regex(target).finditer(norm.text))
        return spans

    def prefilter(self, title: str, flags: dict | None = None) -> tuple[bool, str]:
        """Cheap title-only check used by adapters before fetching job details."""
        gate = self.title_gate(title, flags)
        if gate.status == "reject":
            return False, gate.reason
        domain = self.non_target(gate.norm)
        if domain:
            return False, f"non_target_title:{domain}"
        conditional = gate.status == "conditional"
        if any(self._title_score(c, gate.norm, conditional)[0] > 0 for c in self.all_categories):
            return True, ""
        if self.rules.prefilter_terms.intersection(gate.norm.tokens):
            return True, ""
        return False, "irrelevant_title"

    # ------------------------------------------------------------- scoring
    def _title_score(self, category: Category, norm: NormalizedTitle, conditional: bool) -> tuple[int, str]:
        best, matched = 0, ""
        has_keyword = bool(category.title_keywords) and bool(keyword_hits(norm.text, category.title_keywords))
        for role in self._roles[category.id]:
            if role.requires_title_keyword and not has_keyword:
                continue  # e.g. generic 'Associate Analyst' only counts with a data/analytics word in the title
            if phrase_in_title(norm, role.raw):
                score = role.weight
            elif tokens_in_title(norm, role.raw):
                score = role.weight - TOKEN_MATCH_PENALTY
            else:
                continue
            if score > best:
                best, matched = score, role.raw
        if best == 0 and category.title_keywords:
            hits = keyword_hits(norm.text, category.title_keywords)
            if hits:
                best = CONDITIONAL_TITLE_KEYWORD_WEIGHT if conditional else TITLE_KEYWORD_WEIGHT
                matched = hits[0]
        return best, matched

    def _negative_title(self, category: Category, norm: NormalizedTitle) -> str:
        for term in category.negative_keywords:
            if keyword_hits(norm.text, [term]):
                return term
        for pattern in category.excluded_title_patterns:
            if _compiled(pattern).search(norm.text):
                return pattern
        return ""

    def score(self, category: Category, gate: TitleGate, text: str) -> CategoryScore:
        conditional = gate.status == "conditional"
        title_score, matched_role = self._title_score(category, gate.norm, conditional)
        negative = self._negative_title(category, gate.norm)
        if negative:
            return CategoryScore(category, 0, title_score, [], f"negative_keyword:{negative}")
        phrases = keyword_hits(text, category.negative_description_phrases)
        if phrases:
            return CategoryScore(category, 0, title_score, [], f"negative_phrase:{'; '.join(phrases)}")
        evidence = keyword_hits(f"{gate.norm.raw}\n{text}", category.positive_keywords)
        score = min(100, title_score + min(EVIDENCE_CAP, EVIDENCE_POINTS * len(evidence)))
        matched = ([matched_role] if matched_role else []) + evidence
        return CategoryScore(category, score, title_score, matched)

    # ------------------------------------------------------------ evaluate
    def evaluate(self, job: RawJob) -> Evaluation:
        flags = job.flags or {}
        if flags.get("prefilter"):
            return Evaluation(job, "reject", reason=f"prefilter:{flags['prefilter']}", stage="prefilter")
        gate = self.title_gate(job.title, flags)
        if gate.status == "reject":
            return Evaluation(job, "reject", reason=gate.reason, stage="title")
        domain = self.non_target(gate.norm)
        if domain:
            return Evaluation(job, "reject", reason=f"non_target_title:{domain}", stage="title")

        geo = resolve(job.location, job.country_codes, job.locations, job.description)
        if geo.status == "unknown" and flags.get("geo_hint") == "india":
            geo = GeoResult("india", "inferred", "board search filter")
        if geo.status != "india":
            reason = "non_india" if geo.status == "foreign" else "geo_unknown"
            return Evaluation(job, "reject", reason=reason, stage="geo", geo=geo)

        experience = parse_experience(
            job.requirements_text or job.description, job.preferred_text, title=job.title, min_years=self.min_years, max_years=self.max_years
        )
        if experience.decision == "reject":
            reason = experience.reason or "experience_too_high"
            return Evaluation(job, "reject", reason=reason, stage="experience", geo=geo, experience=experience)

        review_flags: list[str] = []
        notes: list[str] = []
        if gate.status == "conditional":
            if not experience.explicit or experience.min_years is None or experience.min_years > self.max_years:
                return Evaluation(
                    job, "reject", reason=f"conditional_title_unverified:{gate.reason}", stage="title", geo=geo, experience=experience
                )
            review_flags.append(gate.reason)
            notes.append(f"Title suggests seniority ({gate.reason.replace('_', ' ')}) but posting states {experience.label}")
        if experience.decision == "review":
            review_flags.append("conflicting_experience")
            notes.append(experience.note)
        if geo.basis == "inferred":
            review_flags.append("inferred_location")
            notes.append(f"Location inferred ({geo.evidence})")
        if experience.note and experience.decision == "accept" and experience.label.startswith("Preferred"):
            notes.append(experience.note)
        if not job.description and not job.requirements_text:
            notes.append("Description unavailable")

        text = strip_boilerplate(f"{job.requirements_text}\n{job.description}")[:6000]
        main_scores = [self.score(c, gate, text) for c in self.categories]
        tie = self.rules.tie_priority
        ranked = sorted(main_scores, key=lambda s: (-s.score, -tie.get(s.category.id, 0), s.category.id))
        accepted = [s for s in ranked if not s.disqualified and s.score >= ACCEPT_THRESHOLD]

        route = "aggregator" if flags.get("aggregator") else "main"
        if accepted:
            winner = accepted[0]
            also = [f"{s.category.id}:{s.score}" for s in accepted[1:]]
            return self._accept(job, winner, route, geo, experience, review_flags, notes, also)

        if self.adjacent is not None:
            adjacent = self.score(self.adjacent, gate, text)
            if not adjacent.disqualified and adjacent.score >= ACCEPT_THRESHOLD:
                return self._accept(job, adjacent, "aggregator" if route == "aggregator" else "adjacent", geo, experience, review_flags, notes, [])

        best = ranked[0] if ranked else None
        if best and best.disqualified:
            return Evaluation(
                job, "reject", category_id=best.category.id, reason=best.disqualified, stage="role", geo=geo, experience=experience
            )
        if best and best.score >= POSSIBLE_THRESHOLD and self.rules.possible_terms.intersection(gate.norm.tokens):
            return Evaluation(
                job,
                "possible",
                route=route,
                category_id=best.category.id,
                score=best.score,
                tier="possible_match",
                reason="weak_role_match",
                stage="role",
                geo=geo,
                experience=experience,
                matched_terms=best.matched,
                review_flags=review_flags,
                notes=["Possible false negative: weak role match, review manually", *notes],
            )
        return Evaluation(
            job,
            "reject",
            category_id=best.category.id if best else "",
            score=best.score if best else 0,
            reason="weak_role_match",
            stage="role",
            geo=geo,
            experience=experience,
            matched_terms=best.matched if best else [],
        )

    def _accept(self, job, winner: CategoryScore, route, geo, experience, review_flags, notes, also) -> Evaluation:
        tier = "high_confidence" if winner.score >= HIGH_CONFIDENCE_THRESHOLD and not review_flags else "needs_review"
        if also:
            notes = [*notes, f"Exclusive category winner; also matched {', '.join(also)}"]
        return Evaluation(
            job,
            "accept",
            route=route,
            category_id=winner.category.id,
            score=winner.score,
            tier=tier,
            reason="accepted",
            stage="accepted",
            geo=geo,
            experience=experience,
            matched_terms=winner.matched,
            review_flags=review_flags,
            notes=notes,
            also_matched=also,
        )


def _roles(category: Category) -> list[Role]:
    roles: list[Role] = []
    for item in category.target_roles:
        if isinstance(item, dict):
            roles.append(
                Role(
                    str(item.get("title", "")),
                    int(item.get("weight", DEFAULT_ROLE_WEIGHT)),
                    bool(item.get("requires_title_keyword", False)),
                )
            )
        else:
            roles.append(Role(str(item), DEFAULT_ROLE_WEIGHT))
    return [r for r in roles if r.raw]


def _inside(span: Span, spans: list[Span]) -> bool:
    return any(start <= span[0] and span[1] <= end for start, end in spans)


def _hits(pattern: re.Pattern[str], text: str, spans: list[Span]) -> list[re.Match[str]]:
    """Matches of ``pattern`` that are not part of one of the profile's own target titles."""
    return [m for m in pattern.finditer(text) if not _inside(m.span(), spans)]


def _blank(text: str, matches: list[re.Match[str]]) -> str:
    """Blank out matched words while keeping every other character at the same offset."""
    chars = list(text)
    for match in matches:
        chars[match.start():match.end()] = " " * (match.end() - match.start())
    return "".join(chars)


@lru_cache(maxsize=1024)
def _phrase_regex(target: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(target)}(?![a-z0-9])")


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)
