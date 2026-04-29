from __future__ import annotations

from collections import defaultdict

from .models import Board, BoardHealth, Category, JobResult, RawJob, RejectedJob
from .sources.ats import adapter_for, board_from_url
from .text import contains_negative, has_excluded_seniority, is_india_job, parse_experience, role_score


CATEGORY_TIE_PRIORITY = {
    "research": 300,
    "excel_mis": 200,
    "data_bi": 100,
}

POSSIBLE_TITLE_TERMS = (
    "analyst",
    "associate",
    "executive",
    "specialist",
    "research",
    "insights",
    "intelligence",
    "reporting",
    "analytics",
    "business",
    "finance",
    "operations",
    "mis",
    "data",
    "reconciliation",
    "kyc",
    "accounts",
    "procurement",
    "audit",
)

POSSIBLE_EXCLUDED_TITLE_TERMS = (
    "software engineer",
    "engineer",
    "developer",
    "frontend",
    "backend",
    "fullstack",
    "product manager",
    "product management",
    "talent acquisition",
    "sales hiring",
    "recruiter",
)


class JobPipeline:
    def __init__(self, http):
        self.http = http

    def collect_from_boards(self, boards: list[Board]) -> tuple[list[RawJob], list[BoardHealth]]:
        jobs: list[RawJob] = []
        health: list[BoardHealth] = []
        for board in boards:
            try:
                board_jobs = list(adapter_for(board.source, self.http).list_jobs(board))
                jobs.extend(board_jobs)
                health.append(
                    BoardHealth(
                        company=board.company,
                        source=board.source,
                        token=board.token,
                        status="ok" if board_jobs else "empty",
                        jobs_found=len(board_jobs),
                    )
                )
            except Exception as exc:
                health.append(
                    BoardHealth(
                        company=board.company,
                        source=board.source,
                        token=board.token,
                        status="failed",
                        jobs_found=0,
                        error=str(exc),
                    )
                )
        return [job for job in jobs if job.title and job.url], health

    def collect_from_urls(self, urls: list[str]) -> list[RawJob]:
        jobs: list[RawJob] = []
        boards_by_key = {}
        generic = adapter_for("generic_html", self.http)
        for url in urls:
            board = board_from_url(url)
            if board:
                boards_by_key[(board.source, board.token)] = board
            else:
                job = generic.fetch_url(url)
                if job:
                    jobs.append(job)
        board_jobs, _health = self.collect_from_boards(list(boards_by_key.values()))
        jobs.extend(board_jobs)
        return jobs

    def classify(self, jobs: list[RawJob], categories: list[Category], max_per_category: int) -> dict[str, list[JobResult]]:
        buckets: dict[str, list[JobResult]] = defaultdict(list)
        for job in self._dedupe_jobs(jobs):
            winner = self._best_category_match(job, categories)
            if winner:
                buckets[winner.category_id].append(winner)

        for category_id, results in buckets.items():
            results.sort(key=lambda item: (-item.score, item.company.lower(), item.title.lower()))
            buckets[category_id] = results[:max_per_category]
        return buckets

    def discover_false_negatives(
        self,
        jobs: list[RawJob],
        categories: list[Category],
        accepted_buckets: dict[str, list[JobResult]],
        max_possible_per_category: int = 50,
    ) -> tuple[dict[str, list[JobResult]], list[RejectedJob]]:
        accepted_urls = {
            item.url.split("?")[0].rstrip("/").lower()
            for results in accepted_buckets.values()
            for item in results
        }
        possible: dict[str, list[JobResult]] = defaultdict(list)
        rejected: list[RejectedJob] = []

        for job in self._dedupe_jobs(jobs):
            job_key = job.url.split("?")[0].rstrip("/").lower()
            if job_key in accepted_urls:
                continue
            category_evaluations = [self._evaluate_with_reason(job, category) for category in categories]
            category_evaluations.sort(
                key=lambda item: (
                    -item[2],
                    -CATEGORY_TIE_PRIORITY.get(item[0].id, 0),
                    item[0].id,
                )
            )
            category, result, score, reason, experience, matched = category_evaluations[0]
            if result:
                continue
            if reason == "weak_role_match" and score >= 10 and self._is_possible_match_title(job.title):
                possible_result = self._possible_match(job, category, score, experience, matched)
                possible[category.id].append(possible_result)
            rejected.append(
                RejectedJob(
                    company=job.company,
                    title=job.title,
                    url=job.url,
                    source=job.source,
                    location=job.location,
                    category_id=category.id,
                    score=score,
                    reason=reason,
                    experience_required=experience,
                    matched_terms=matched,
                    retrieved_at=job.retrieved_at,
                )
            )

        for category_id, results in possible.items():
            results.sort(key=lambda item: (-item.score, item.company.lower(), item.title.lower()))
            possible[category_id] = results[:max_possible_per_category]
        return possible, rejected

    def _is_possible_match_title(self, title: str) -> bool:
        lowered = title.lower()
        if any(term in lowered for term in POSSIBLE_EXCLUDED_TITLE_TERMS):
            return False
        return any(term in lowered for term in POSSIBLE_TITLE_TERMS)

    def _best_category_match(self, job: RawJob, categories: list[Category]) -> JobResult | None:
        candidates = []
        for category in categories:
            result = self._evaluate(job, category)
            if result:
                candidates.append(result)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                -item.score,
                -CATEGORY_TIE_PRIORITY.get(item.category_id, 0),
                item.category_id,
            )
        )
        winner = candidates[0]
        if len(candidates) > 1:
            loser_names = ", ".join(f"{item.category_id}:{item.score}" for item in candidates[1:])
            note = f"Exclusive category winner; also matched {loser_names}"
            winner.system_notes = f"{winner.system_notes}; {note}".strip("; ")
        return winner

    def _evaluate(self, job: RawJob, category: Category) -> JobResult | None:
        _category, result, _score, _reason, _experience, _matched = self._evaluate_with_reason(job, category)
        return result

    def _evaluate_with_reason(self, job: RawJob, category: Category) -> tuple[Category, JobResult | None, int, str, str, list[str]]:
        combined = f"{job.title} {job.description}"
        if has_excluded_seniority(job.title):
            return category, None, 0, "excluded_seniority", "", []

        negatives = contains_negative(combined, category.negative_keywords)
        if negatives:
            return category, None, 0, f"negative_keyword:{'; '.join(negatives)}", "", []

        score, matched = role_score(job.title, job.description, category.target_roles, category.positive_keywords)

        if not is_india_job(job.location, job.description):
            return category, None, score, "non_india", "", matched

        allowed, experience, exp_note = parse_experience(job.description)
        if not allowed:
            return category, None, score, "experience_too_high", experience, matched

        if score < 45:
            return category, None, score, "weak_role_match", experience, matched

        notes = exp_note
        if not job.description:
            notes = "Description unavailable"
        quality_tier = "high_confidence" if score >= 70 else "needs_review"

        return category, JobResult(
            company=job.company,
            title=job.title,
            experience_required=experience,
            url=job.url,
            system_notes=notes,
            category_id=category.id,
            score=score,
            source=job.source,
            location=job.location,
            matched_terms=matched,
            retrieved_at=job.retrieved_at,
            quality_tier=quality_tier,
        ), score, "accepted", experience, matched

    def _possible_match(
        self,
        job: RawJob,
        category: Category,
        score: int,
        experience: str,
        matched: list[str],
    ) -> JobResult:
        return JobResult(
            company=job.company,
            title=job.title,
            experience_required=experience or "Unspecified",
            url=job.url,
            system_notes="Possible false negative: weak role match, review manually",
            category_id=category.id,
            score=score,
            source=job.source,
            location=job.location,
            matched_terms=matched,
            retrieved_at=job.retrieved_at,
            quality_tier="possible_match",
        )

    def _dedupe_jobs(self, jobs: list[RawJob]) -> list[RawJob]:
        seen = set()
        output = []
        for job in jobs:
            key = (job.url.split("?")[0].rstrip("/").lower(), job.title.lower(), job.company.lower())
            if key not in seen:
                seen.add(key)
                output.append(job)
        return output
