"""Collection, evaluation, de-duplication and routing of jobs."""

from __future__ import annotations

import logging
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .classifier import Classifier, Evaluation
from .geo import classify_segment, first_india_segment, primary_india_city
from .http import FetchError, HttpClient
from .models import Board, BoardHealth, JobResult, RawJob, RejectedJob, legacy_url_key
from .sources import AdapterContext, adapter_for, board_from_url
from .text import normalize_title, strip_boilerplate, truncate

log = logging.getLogger(__name__)

SOURCE_PRIORITY = {
    "lever": 0, "greenhouse": 0, "ashby": 0, "smartrecruiters": 1, "workday": 1, "amazon_jobs": 1,
    "oracle_hcm": 1, "eightfold": 1, "accenture": 2, "capgemini": 2, "tcs_ibegin": 2, "successfactors": 2,
    "paginated_html": 3, "generic_html": 4, "linkedin_guest": 5,
}
HOST_SCOPED_SOURCES = {"paginated_html", "successfactors", "generic_html"}
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:inc|ltd|limited|llc|llp|plc|pvt|private|corp|corporation|co|company|group|india|global|services|technologies|technology|solutions)\b"
)


@dataclass
class RunBuckets:
    main: dict[str, list[JobResult]] = field(default_factory=dict)
    overflow: dict[str, list[JobResult]] = field(default_factory=dict)
    possible: dict[str, list[JobResult]] = field(default_factory=dict)
    adjacent: list[JobResult] = field(default_factory=list)
    aggregator: list[JobResult] = field(default_factory=list)
    rejected: list[RejectedJob] = field(default_factory=list)

    def recorded(self) -> list[JobResult]:
        """Everything that is persisted in state (all accepted routes, incl. overflow)."""
        rows: list[JobResult] = []
        for bucket in (self.main, self.overflow):
            for items in bucket.values():
                rows.extend(items)
        return rows + self.adjacent + self.aggregator

    def all_listed(self) -> list[JobResult]:
        rows = self.recorded()
        for items in self.possible.values():
            rows.extend(items)
        return rows


class JobPipeline:
    def __init__(
        self,
        http: HttpClient,
        classifier: Classifier,
        *,
        workers: int = 8,
        board_budget_s: float = 120.0,
        max_per_category: int = 40,
        per_company_cap: int = 8,
        max_possible_per_category: int = 50,
    ):
        self.http = http
        self.classifier = classifier
        self.workers = max(1, workers)
        self.board_budget_s = board_budget_s
        self.max_per_category = max_per_category
        self.per_company_cap = per_company_cap
        self.max_possible_per_category = max_possible_per_category

    # -------------------------------------------------------- collection
    def collect_from_boards(self, boards: list[Board], quarantined: dict[str, str] | None = None) -> tuple[list[RawJob], list[BoardHealth]]:
        quarantined = quarantined or {}
        results: list[tuple[list[RawJob], BoardHealth]] = [([], None)] * len(boards)  # type: ignore[list-item]
        runnable: list[tuple[int, Board]] = []
        for index, board in enumerate(boards):
            if board.key in quarantined:
                results[index] = ([], _health(board, "quarantined", note=f"quarantined until {quarantined[board.key][:10]}"))
            else:
                runnable.append((index, board))
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="board") as pool:
            futures = {pool.submit(self._collect_board, board): index for index, board in runnable}
            for future, index in futures.items():
                results[index] = future.result()
        jobs: list[RawJob] = []
        health: list[BoardHealth] = []
        for board_jobs, board_health in results:
            jobs.extend(board_jobs)
            health.append(board_health)
        return jobs, health

    def _collect_board(self, board: Board) -> tuple[list[RawJob], BoardHealth]:
        started = time.monotonic()
        context = AdapterContext(prefilter=self.classifier.prefilter, budget_s=self.board_budget_s)
        try:
            adapter = adapter_for(board.source, self.http, context)
            jobs = [job for job in adapter.list_jobs(board) if job.title and job.url]
        except FetchError as exc:
            log.warning("Board failed: %s (%s) %s", board.company, board.source, exc)
            return [], _health(board, "failed", error=str(exc), hard=exc.hard, duration=time.monotonic() - started)
        except Exception as exc:  # adapter bug or unexpected payload: isolate per board
            log.exception("Board crashed: %s (%s)", board.company, board.source)
            return [], _health(board, "failed", error=f"{type(exc).__name__}: {exc}", duration=time.monotonic() - started)
        for job in jobs:
            _stamp(job, board)
        status = "partial" if adapter.partial else ("ok" if jobs else "empty")
        note = "; ".join(adapter.notes)
        log.info("Board %-28s %-15s %-7s %4d jobs in %.1fs", board.company[:28], board.source, status, len(jobs), time.monotonic() - started)
        return jobs, _health(board, status, jobs_found=len(jobs), duration=time.monotonic() - started, note=note)

    def collect_from_urls(self, urls: list[str]) -> tuple[list[RawJob], list[BoardHealth]]:
        boards: dict[str, Board] = {}
        for url in urls:
            board = board_from_url(url) or Board(company=urlparse(url).netloc, source="generic_html", token=url)
            boards.setdefault(board.key, board)
        return self.collect_from_boards(list(boards.values()))

    # -------------------------------------------------------- evaluation
    def evaluate(self, jobs: list[RawJob]) -> list[Evaluation]:
        return [self.classifier.evaluate(job) for job in dedupe_raw(jobs)]

    def build(self, evaluations: list[Evaluation]) -> RunBuckets:
        buckets = RunBuckets()
        accepted: list[JobResult] = []
        possible: list[JobResult] = []
        for ev in evaluations:
            if ev.decision == "reject":
                buckets.rejected.append(to_rejected(ev))
            elif ev.decision == "possible":
                possible.append(to_result(ev))
            else:
                accepted.append(to_result(ev))

        accepted = group_duplicates(accepted)
        accepted_fps = {fingerprint(r) for r in accepted}
        possible = [r for r in group_duplicates(possible) if fingerprint(r) not in accepted_fps]

        by_category: dict[str, list[JobResult]] = defaultdict(list)
        for result in accepted:
            if result.route == "adjacent":
                buckets.adjacent.append(result)
            elif result.route == "aggregator":
                buckets.aggregator.append(result)
            else:
                by_category[result.category_id].append(result)
        for category in self.classifier.categories:
            rows = sorted(by_category.get(category.id, []), key=_rank)
            kept, overflow = apply_caps(rows, self.max_per_category, self.per_company_cap)
            buckets.main[category.id] = kept
            buckets.overflow[category.id] = overflow
        buckets.adjacent.sort(key=_rank)
        buckets.aggregator.sort(key=_rank)

        by_possible: dict[str, list[JobResult]] = defaultdict(list)
        for result in possible:
            by_possible[result.category_id].append(result)
        for category in self.classifier.categories:
            buckets.possible[category.id] = sorted(by_possible.get(category.id, []), key=_rank)[: self.max_possible_per_category]
        return buckets


# ------------------------------------------------------------------ helpers
def _health(board: Board, status: str, jobs_found: int = 0, error: str = "", hard: bool = False, duration: float = 0.0, note: str = "") -> BoardHealth:
    return BoardHealth(
        company=board.company,
        source=board.source,
        token=board.token,
        status=status,
        jobs_found=jobs_found,
        error=error,
        duration_s=round(duration, 1),
        hard_failure=hard,
        board_key=board.key,
        note=note,
    )


def _stamp(job: RawJob, board: Board) -> None:
    job.board_key = board.key
    if not job.company:
        job.company = board.company
    if board.aggregator:
        job.flags["aggregator"] = True
    if not job.stable_key and job.source in HOST_SCOPED_SOURCES:
        host = urlparse(job.url).netloc.lower()
        job.stable_key = f"{job.source}:{host}:{job.source_id}" if job.source_id else legacy_url_key(job.url)


def dedupe_raw(jobs: list[RawJob]) -> list[RawJob]:
    """Exact-key de-duplication (e.g. overlapping keyword boards); keep the richer copy."""
    best: dict[str, RawJob] = {}
    order: list[str] = []
    for job in jobs:
        key = job.key()
        current = best.get(key)
        if current is None:
            best[key] = job
            order.append(key)
        elif len(job.description) > len(current.description):
            best[key] = job
    return [best[key] for key in order]


def to_result(ev: Evaluation) -> JobResult:
    job = ev.job
    location = job.location or "; ".join(job.locations[:3])
    if job.location and job.locations and classify_segment(job.location)[0] != "india":
        india = first_india_segment(job.locations)  # multi-location job: show the Indian office first
        if india:
            location = f"{india} (also {job.location})"
    snippet_source = job.requirements_text or job.description
    return JobResult(
        company=job.company,
        title=job.title,
        experience_required=ev.experience_label or "Unspecified",
        url=job.url,
        system_notes="; ".join(dict.fromkeys(n for n in ev.notes if n)),
        category_id=ev.category_id,
        score=ev.score,
        source=job.source,
        location=location,
        matched_terms=ev.matched_terms,
        retrieved_at=job.retrieved_at,
        quality_tier=ev.tier,
        key=job.key(),
        route=ev.route,
        posted_date=job.posted_date,
        geo_basis=ev.geo.basis if ev.geo else "",
        exp_evidence=ev.experience.evidence if ev.experience else "",
        review_flags=list(ev.review_flags),
        board_key=job.board_key,
        legacy_keys=job.all_legacy_keys(),
        url_kind=job.url_kind,
        description_snippet=truncate(strip_boilerplate(snippet_source), 700),
    )


def to_rejected(ev: Evaluation) -> RejectedJob:
    job = ev.job
    return RejectedJob(
        company=job.company,
        title=job.title,
        url=job.url,
        source=job.source,
        location=job.location or "; ".join(job.locations[:3]),
        category_id=ev.category_id,
        score=ev.score,
        reason=ev.reason,
        experience_required=ev.experience_label,
        matched_terms=ev.matched_terms,
        retrieved_at=job.retrieved_at,
        stage=ev.stage,
        key=job.key(),
        geo_basis=ev.geo.basis if ev.geo else "",
    )


def company_norm(company: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (company or "").lower())
    text = _COMPANY_SUFFIX_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip() or (company or "").lower()


def fingerprint(result: JobResult) -> tuple[str, str, str]:
    return (company_norm(result.company), normalize_title(result.title).text, primary_india_city([result.location]))


def group_duplicates(results: list[JobResult]) -> list[JobResult]:
    """Collapse the same role at the same company and city (cross-source or multi-requisition)."""
    groups: dict[tuple[str, str, str], list[JobResult]] = defaultdict(list)
    order: list[tuple[str, str, str]] = []
    for result in results:
        fp = fingerprint(result)
        if fp not in groups:
            order.append(fp)
        groups[fp].append(result)
    output: list[JobResult] = []
    for fp in order:
        members = groups[fp]
        members.sort(key=lambda r: (SOURCE_PRIORITY.get(r.source, 9), -r.score, r.url))
        keeper = members[0]
        others = [m for m in members[1:] if m.key != keeper.key]
        if others:
            keeper.group_keys = list(dict.fromkeys(m.key for m in others))
            keeper.group_urls = list(dict.fromkeys(m.url for m in others if m.url != keeper.url))
            if keeper.group_urls:
                shown = "; ".join(keeper.group_urls[:3])
                more = f" (+{len(keeper.group_urls) - 3} more)" if len(keeper.group_urls) > 3 else ""
                note = f"+{len(keeper.group_urls)} more opening(s)/posting(s): {shown}{more}"
                keeper.system_notes = "; ".join(x for x in (keeper.system_notes, note) if x)
        output.append(keeper)
    return output


def _rank(result: JobResult) -> tuple:
    posted = int(result.posted_date.replace("-", "")) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", result.posted_date or "") else 0
    return (-result.score, -posted, result.company.lower(), result.title.lower())


def apply_caps(rows: list[JobResult], max_rows: int, per_company: int) -> tuple[list[JobResult], list[JobResult]]:
    kept: list[JobResult] = []
    overflow: list[JobResult] = []
    counts: Counter[str] = Counter()
    for row in rows:
        company = company_norm(row.company)
        if len(kept) < max_rows and counts[company] < per_company:
            kept.append(row)
            counts[company] += 1
        else:
            overflow.append(row)
    return kept, overflow
