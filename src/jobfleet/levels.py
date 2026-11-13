"""Named seniority levels and job domains that a profile switches on or off.

A *level* is a seniority signal in a job title ("Senior", "Lead", "Intern").
For each level a profile chooses an action:

- ``allow``       - the word does not matter
- ``conditional`` - keep the job only if the posting states a minimum
                    experience within the profile's range (tier: needs_review)
- ``exclude``     - drop the job

A *domain* is a family of titles (engineering, sales, design...) that is
excluded unless one of the profile's role families owns it. All patterns run
on normalised, lowercase titles (see ``text.normalize_title``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ACTIONS = ("allow", "conditional", "exclude")


@dataclass(frozen=True)
class Level:
    name: str
    label: str
    pattern: re.Pattern[str]
    description: str


def _level(name: str, label: str, pattern: str, description: str) -> Level:
    return Level(name, label, re.compile(pattern), description)


# Order matters: it is the order in which titles are checked and reasons reported.
LEVELS: dict[str, Level] = {
    lvl.name: lvl
    for lvl in (
        _level("intern", "intern", r"\b(?:interns?|internships?)\b", "Internships"),
        _level(
            "entry_program",
            "entry programme",
            r"\b(?:trainees?|apprentices?|apprenticeship|graduates?|campus|pass ?outs?|20\d\d batch|batch (?:of )?20\d\d)\b",
            "Trainee, apprentice, graduate and campus programmes",
        ),
        _level("junior", "junior", r"\bjunior\b", "Titles that say Junior / Jr"),
        _level("junior_manager", "junior manager", r"\b(?:assistant|associate|deputy|asst)\s+manager\b", "Assistant/Associate/Deputy Manager"),
        _level("senior", "senior", r"\bsenior\b", "Titles that say Senior / Sr"),
        _level("vp", "vice president", r"\bvice president\b|\b(?:a|d|s|e)?vp\b", "VP, AVP, SVP"),
        _level("director", "director", r"\bdirector\b", "Director titles"),
        _level("chief", "chief", r"\bchief\b", "Chief / C-level"),
        _level("principal", "principal", r"\bprincipal\b", "Principal titles"),
        _level("head", "head", r"\bhead of\b|\bhead\b(?=\s*(?:-|,|$))|^head\b", "Head of ..."),
        _level("architect", "architect", r"\barchitect\b", "Architect titles"),
        _level("lead", "lead", r"\blead(?:er|ers|ership)?\b(?!\s+(?:generation|gen)\b)|\btl\b", "Lead / Team Lead (not 'Lead Generation')"),
        _level("staff", "staff", r"\bstaff\b(?!\s+accountant)", "Staff-level (not 'Staff Accountant')"),
        _level("manager", "manager", r"\bmanager\b", "Manager titles"),
    )
}
LEVEL_3_PLUS = "level_3_plus"  # roman/numbered levels III and above ("Analyst III")
ALL_LEVEL_NAMES = (*LEVELS, LEVEL_3_PLUS)

_SENIOR_UP = ("vp", "director", "chief", "principal", "head", "architect", "lead", "staff", "manager")

# Seniority presets: what each level means for someone at that stage.
LEVEL_PRESETS: dict[str, dict[str, str]] = {
    "student": {
        "intern": "allow", "entry_program": "allow", "junior": "allow", "junior_manager": "exclude", "senior": "exclude",
        **{name: "exclude" for name in _SENIOR_UP}, LEVEL_3_PLUS: "exclude",
    },
    "early_career": {
        "intern": "exclude", "entry_program": "allow", "junior": "allow", "junior_manager": "conditional", "senior": "conditional",
        **{name: "exclude" for name in _SENIOR_UP}, LEVEL_3_PLUS: "conditional",
    },
    "mid": {
        "intern": "exclude", "entry_program": "exclude", "junior": "allow", "junior_manager": "allow", "senior": "allow",
        "lead": "conditional", "staff": "conditional", "manager": "conditional", "architect": "conditional",
        "principal": "exclude", "head": "exclude", "director": "exclude", "vp": "exclude", "chief": "exclude", LEVEL_3_PLUS: "allow",
    },
    "senior": {
        "intern": "exclude", "entry_program": "exclude", "junior": "exclude", "junior_manager": "allow", "senior": "allow",
        "lead": "allow", "staff": "allow", "manager": "allow", "architect": "allow", "principal": "allow",
        "head": "conditional", "director": "conditional", "vp": "exclude", "chief": "exclude", LEVEL_3_PLUS: "allow",
    },
    "leadership": {
        "intern": "exclude", "entry_program": "exclude", "junior": "exclude", "junior_manager": "exclude", "senior": "allow",
        **{name: "allow" for name in _SENIOR_UP}, LEVEL_3_PLUS: "allow",
    },
}
DEFAULT_YEARS = {"student": (0, 1), "early_career": (0, 3), "mid": (3, 7), "senior": (6, 15), "leadership": (10, 30)}


@dataclass(frozen=True)
class Domain:
    name: str
    pattern: re.Pattern[str]
    exception: re.Pattern[str] | None
    description: str


def _domain(name: str, pattern: str, description: str, exception: str | None = None) -> Domain:
    return Domain(name, re.compile(pattern), re.compile(exception) if exception else None, description)


DOMAINS: dict[str, Domain] = {
    d.name: d
    for d in (
        _domain(
            "it_operations",
            r"\b(?:security|soc|cyber\s*security|cybersecurity|endpoint|network|it|cloud|infrastructure|talent|people"
            r"|technical support|it support|support|platform|devops|noc|service desk|desktop|site reliability)\s+operations\b",
            "IT, security and support operations",
        ),
        _domain(
            "security",
            r"\b(?:soc|siem|cyber|cybersecurity|penetration|vulnerability|threat|malware|forensics?|infosec)\b"
            r"|\binformation security\b|\bsecurity (?:analyst|engineer|risk|specialist|consultant|associate)\b",
            "Cyber/information security",
        ),
        _domain(
            "it_systems",
            r"\b(?:l|s|p)?mts\b|\bmember of technical staff\b|\b(?:business )?systems analyst\b|\bservicenow\b"
            r"|\b(?:integration|middleware|event mesh)\b|\bsap (?:basis|abap|fiori|integration|security|bw|hana|btp|cpi|technical)\b",
            "IT systems, ERP and integration",
        ),
        _domain("engineering", r"\b(?:engineers?|engineering|developers?|programmer|sde|sdet|devops|sre|coder)\b", "Software/hardware engineering"),
        _domain("recruiting", r"\b(?:recruiters?|recruitment|recruiting|talent acquisition|sourcer|headhunter)\b", "Recruiting"),
        _domain(
            "non_office",
            r"\b(?:nurse|nursing|physician|doctor|pharmacist|dentist|therapist|driver|technician|mechanic|electrician"
            r"|plumber|chef|cook|teacher|tutor|lecturer|professor|security guard|housekeeping)\b",
            "Healthcare, trades, teaching and other non-office roles",
        ),
        _domain(
            "sales",
            r"\b(?:sales|business development|inside sales)\s+(?:executive|representative|rep|associate|specialist|officer)\b|\baccount executive\b",
            "Sales",
        ),
        _domain(
            "customer_support",
            r"\b(?:customer (?:service|support|success|care)|call cent(?:er|re)|tele ?caller|voice process|chat process)\b",
            "Customer service and success",
        ),
        _domain("design", r"\bdesigner\b", "Design"),
        _domain("content", r"\b(?:content writer|copywriter|copy writer|video editor|editor)\b", "Writing and editing"),
        _domain("data_science_ml", r"\b(?:scientist|machine learning|ml|deep learning|computer vision|nlp)\b", "Data science and ML"),
        _domain("legal", r"\b(?:legal counsel|lawyer|attorney|paralegal|advocate)\b", "Legal"),
        _domain("qa_testing", r"\b(?:quality|qa|test) (?:analyst|auditor|associate|specialist|engineer)\b", "QA and testing", r"\bdata quality\b"),
        _domain("hr", r"\bhr (?:team|business partner)\b|\bhuman resources\b", "HR", r"\b(?:hr|people|workforce) analytics\b"),
        _domain("martech", r"\bmarketing technology\b|\bmartech\b", "Marketing technology"),
    )
}


def level_actions(preset: str, overrides: dict[str, str] | None = None) -> dict[str, str]:
    actions = dict(LEVEL_PRESETS[preset])
    actions.update(overrides or {})
    return actions
