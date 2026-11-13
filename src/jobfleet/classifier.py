"""Job classification: title gate -> geo -> experience -> category scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .experience import ExperienceResult, parse_experience
from .geo import GeoResult, resolve
from .models import Category, RawJob
from .text import NormalizedTitle, keyword_hits, normalize_title, phrase_in_title, strip_boilerplate, tokens_in_title

CATEGORY_TIE_PRIORITY = {"research": 300, "excel_mis": 200, "data_bi": 100, "adjacent": 0}
ACCEPT_THRESHOLD = 55
HIGH_CONFIDENCE_THRESHOLD = 75
POSSIBLE_THRESHOLD = 30
DEFAULT_ROLE_WEIGHT = 60
TOKEN_MATCH_PENALTY = 10
TITLE_KEYWORD_WEIGHT = 35
CONDITIONAL_TITLE_KEYWORD_WEIGHT = 50
EVIDENCE_POINTS = 5
EVIDENCE_CAP = 25
LIMIT_YEARS = 3

_ENTRY_RE = re.compile(
    r"\b(?:trainees?|apprentices?|apprenticeship|graduates?|campus|interns?|internships?|pass ?outs?|20\d\d batch|batch (?:of )?20\d\d)\b"
)
_JUNIOR_MANAGER_RE = re.compile(r"\b(?:assistant|associate|deputy|asst)\s+manager\b")
_SENIOR_RE = re.compile(r"\bsenior\b")
_SENIOR_ALLOWED_RE = re.compile(r"\bsenior\s+(?:[a-z]+\s+){0,3}?(?:analyst|associate|executive)\b")
_HARD_EXCLUDE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("vice president", re.compile(r"\bvice president\b|\b(?:a|d|s|e)?vp\b")),
    ("director", re.compile(r"\bdirector\b")),
    ("chief", re.compile(r"\bchief\b")),
    ("principal", re.compile(r"\bprincipal\b")),
    ("head", re.compile(r"\bhead of\b|\bhead\b(?=\s*(?:-|,|$))|^head\b")),
    ("architect", re.compile(r"\barchitect\b")),
    ("lead", re.compile(r"\blead(?:er|ers|ership)?\b(?!\s+(?:generation|gen)\b)|\btl\b")),
    ("staff", re.compile(r"\bstaff\b(?!\s+accountant)")),
    ("manager", re.compile(r"\bmanager\b")),
)
_NON_TARGET: tuple[tuple[str, re.Pattern[str], re.Pattern[str] | None], ...] = (
    (
        "it/security operations",
        re.compile(
            r"\b(?:security|soc|cyber\s*security|cybersecurity|endpoint|network|it|cloud|infrastructure|talent|people"
            r"|technical support|it support|support|platform|devops|noc|service desk|desktop|site reliability)\s+operations\b"
        ),
        None,
    ),
    (
        "security",
        re.compile(
            r"\b(?:soc|siem|cyber|cybersecurity|penetration|vulnerability|threat|malware|forensics?|infosec)\b"
            r"|\binformation security\b|\bsecurity (?:analyst|engineer|risk|specialist|consultant|associate)\b"
        ),
        None,
    ),
    (
        "it systems",
        re.compile(
            r"\b(?:l|s|p)?mts\b|\bmember of technical staff\b|\b(?:business )?systems analyst\b|\bservicenow\b"
            r"|\b(?:integration|middleware|event mesh)\b|\bsap (?:basis|abap|fiori|integration|security|bw|hana|btp|cpi|technical)\b"
        ),
        None,
    ),
    (
        "engineering",
        re.compile(r"\b(?:engineers?|engineering|developers?|programmer|sde|sdet|devops|sre|coder)\b"),
        re.compile(r"\bbusiness intelligence engineer\b|\bdashboard developer\b|\bspreadsheet developer\b"),
    ),
    ("recruiting", re.compile(r"\b(?:recruiters?|recruitment|recruiting|talent acquisition|sourcer|headhunter)\b"), None),
    (
        "non-office",
        re.compile(
            r"\b(?:nurse|nursing|physician|doctor|pharmacist|dentist|therapist|driver|technician|mechanic|electrician"
            r"|plumber|chef|cook|teacher|tutor|lecturer|professor|security guard|housekeeping)\b"
        ),
        None,
    ),
    (
        "sales/support",
        re.compile(
            r"\b(?:sales|business development|inside sales)\s+(?:executive|representative|rep|associate|specialist|officer)\b"
            r"|\baccount executive\b|\b(?:customer (?:service|support|success|care)|call cent(?:er|re)|tele ?caller"
            r"|voice process|chat process)\b"
        ),
        None,
    ),
    ("design/content", re.compile(r"\bdesigner\b|\b(?:content writer|copywriter|copy writer|video editor|editor)\b"), None),
    ("science/ml", re.compile(r"\b(?:scientist|machine learning|ml|deep learning|computer vision|nlp)\b"), None),
    ("legal", re.compile(r"\b(?:legal counsel|lawyer|attorney|paralegal|advocate)\b"), None),
    (
        "qa/hr/martech",
        re.compile(
            r"\b(?:quality|qa|test) (?:analyst|auditor|associate|specialist|engineer)\b|\bhr (?:team|business partner)\b"
            r"|\bhuman resources\b|\bmarketing technology\b|\bmartech\b"
        ),
        re.compile(r"\bdata quality\b|\b(?:hr|people|workforce) analytics\b"),
    ),
)
# Titles worth a detail-page fetch even without a target-role match (kept narrow: detail calls are the slow part).
PREFILTER_TERMS = frozenset(
    {
        "analyst", "analytics", "research", "insights", "intelligence", "reporting", "mis", "data", "reconciliation",
        "kyc", "accounts", "procurement", "finance", "financial", "excel", "dashboard",
    }
)
POSSIBLE_TITLE_TERMS = frozenset(
    {
        "analyst", "associate", "executive", "specialist", "research", "insights", "intelligence", "reporting",
        "analytics", "business", "finance", "operations", "mis", "data", "reconciliation", "kyc", "accounts",
        "procurement", "audit", "consultant", "coordinator", "officer",
    }
)


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


class Classifier:
    def __init__(self, categories: list[Category], adjacent: Category | None = None):
        self.categories = [c for c in categories if c.route == "main"]
        self.adjacent = adjacent
        self._roles = {c.id: _roles(c) for c in self.all_categories}

    @property
    def all_categories(self) -> list[Category]:
        return self.categories + ([self.adjacent] if self.adjacent else [])

    # ------------------------------------------------------------ title gate
    def title_gate(self, title: str, flags: dict | None = None) -> TitleGate:
        flags = flags or {}
        norm = normalize_title(title)
        text = norm.text
        if flags.get("intern") or flags.get("university"):
            return TitleGate("reject", "excluded_entry_title:" + ("intern" if flags.get("intern") else "university"), norm)
        level_flag = str(flags.get("experience_level") or "").lower()
        if level_flag in {"internship", "intern"}:
            return TitleGate("reject", "excluded_entry_title:internship", norm)
        if level_flag in {"director", "executive", "vp", "c_level"}:
            return TitleGate("reject", f"excluded_seniority:{level_flag}", norm)
        if flags.get("people_manager"):
            return TitleGate("reject", "excluded_seniority:people_manager", norm)
        entry = _ENTRY_RE.search(text)
        if entry:
            return TitleGate("reject", f"excluded_entry_title:{entry.group(0)}", norm)

        conditional: list[str] = []
        working = text
        if _JUNIOR_MANAGER_RE.search(working):
            conditional.append("junior_manager_title")
            working = _JUNIOR_MANAGER_RE.sub(" ", working)
        if _SENIOR_RE.search(working):
            if _SENIOR_ALLOWED_RE.search(working) and not any(p.search(working) for _n, p in _HARD_EXCLUDE):
                conditional.append("senior_title")
                working = _SENIOR_RE.sub(" ", working)
            else:
                return TitleGate("reject", "excluded_seniority:senior", norm)
        for name, pattern in _HARD_EXCLUDE:
            if pattern.search(working):
                return TitleGate("reject", f"excluded_seniority:{name}", norm)
        if norm.level and norm.level >= 3:
            conditional.append(f"level_{norm.level}_title")
        if conditional:
            return TitleGate("conditional", "+".join(conditional), norm)
        return TitleGate("ok", "", norm)

    def non_target(self, norm: NormalizedTitle) -> str:
        for name, pattern, exception in _NON_TARGET:
            if pattern.search(norm.text) and not (exception and exception.search(norm.text)):
                return name
        return ""

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
        if PREFILTER_TERMS.intersection(gate.norm.tokens):
            return True, ""
        return False, "irrelevant_title"

    # ------------------------------------------------------------- scoring
    def _title_score(self, category: Category, norm: NormalizedTitle, conditional: bool) -> tuple[int, str]:
        best, matched = 0, ""
        has_keyword = bool(category.title_keywords) and bool(keyword_hits(norm.text, category.title_keywords))
        for role in self._roles[category.id]:
            if role.requires_title_keyword and not has_keyword:
                continue  # generic 'Associate Analyst' only counts for Data & BI with a data/analytics word
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

        experience = parse_experience(job.requirements_text or job.description, job.preferred_text, title=job.title)
        if experience.decision == "reject":
            return Evaluation(job, "reject", reason="experience_too_high", stage="experience", geo=geo, experience=experience)

        review_flags: list[str] = []
        notes: list[str] = []
        if gate.status == "conditional":
            if not experience.explicit or experience.min_years is None or experience.min_years > LIMIT_YEARS:
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
        ranked = sorted(main_scores, key=lambda s: (-s.score, -CATEGORY_TIE_PRIORITY.get(s.category.id, 0), s.category.id))
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
        if (
            best
            and best.score >= POSSIBLE_THRESHOLD
            and POSSIBLE_TITLE_TERMS.intersection(gate.norm.tokens)
        ):
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


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)
