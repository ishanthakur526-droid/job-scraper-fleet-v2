# Changelog

## 3.0.0 - 2026-11-13

A full audit of v2 against its own outputs (709-row history, 10,775-row rejected-jobs audit from the 2026-11-13 run) and live probes of every source found the defects below. Each fix has a regression test.

### Fixed

| # | Defect in v2 | Evidence | Fix |
| --- | --- | --- | --- |
| 1 | Amazon links used an internal UUID (`id`) instead of the public job id | All 202 Amazon rows in history; those links return HTTP 404 | Links come from `job_path` (numeric `id_icims`); old UUID links kept as aliases so history migrates |
| 2 | India check was a substring test, so `"india"` matched **Indiana**/Indianapolis; "Remote" + any "india" in the description passed | 17 US jobs (Indianapolis, Carmel, "Remote - Indiana", "Remote - United States") passed the check on 2026-11-13 | New `geo.py`: structured country codes, segment-wise word-boundary gazetteer, foreign-marker guards |
| 3 | India jobs rejected: Workday "2 Locations" rows never fetched details; many cities missing; `IND-BLR-...`, `Vadodara, GJ, in` unrecognised | 122+ "N Locations" rows, Lucknow/Coimbatore/Kochi/Vizag/... rejected as non-India | Detail fetch for unknown locations; ~250-place gazetteer incl. aliases and IT parks |
| 4 | Negative keywords matched anywhere in the description | 90 rejections incl. "Active **Director**y", "report to the Director", "principal responsibilities" (e.g. a Mumbai FP&A analyst role) | Seniority is judged on the title only, with whole-word rules |
| 5 | Positive keywords were substrings | "excel" in *excellent*, "mis" in *mission*, "equity" in DEI boilerplate, "pivot" in *pivotal* | Whole-word phrase matching; EEO/benefits/about-us sentences ignored |
| 6 | Experience regex had no context | "over 45 years" (company history) rejected FactSet's Hyderabad analyst role; "100+ years" read as "00+"; "1.5+" read as "5+"; preferred qualifications could reject | Context-aware parser: requirement cues, company-history/age/internal-mobility vetoes, preferred sections, degree alternatives, title-stated experience, conflict -> needs_review |
| 7 | Two-word roles never matched in another order; "Operations Analyst" admitted SOC/IT roles | "Analyst, Data" rejected; Security/Endpoint Operations analysts accepted into Excel/MIS | Order-independent title matching; excluded IT/security/engineering/sales/support domains |
| 8 | Lists were truncated to 40 after scoring; the rest vanished and were later marked "missing" | Amazon filled 25 of 40 Data & BI slots daily | Max 8 per company and 40 per list, rest in `overflow\`; every accepted job is recorded |
| 9 | SmartRecruiters read only the first 100 *global* postings; Workday read 100 via a text search for "India" (which also matches "Remote - Indiana") | Bosch: 594 India postings of 5,093 | `country=in` paging; Workday India country facet (nested and custom facets) |
| 10 | urllib client: retried 404s, crashed on dropped connections, ran sequentially, put full URLs (with keys) in errors | Salesforce failed every run; a run took ~42 minutes | curl_cffi with a Chrome TLS fingerprint, transient-only retries with backoff, parallel boards, secret redaction - a run now takes ~2.5 minutes |
| 11 | The Codex company scout had produced nothing since 2026-06-08 and reported the stale file as success; board discovery probed ~100 dead candidates every day with 0 accepted | 0-byte scout logs | Codex removed; Claude scout runs weekly with deterministic verification and a 30-day negative cache; daily search/token-guessing discovery removed |
| 12 | Dead boards | TCS API moved (HTTP 406), LTIMindtree domain gone, PhonePe/OakNorth/JioStar 404, Highspot/Deel empty | TCS adapter rebuilt for the new iBegin API; dead boards removed; automatic quarantine |
| 13 | A CSV open in Excel could abort the run or make yesterday's jobs look new; writes were not atomic | `job_history_new.csv` written but never read | History moved to SQLite (atomic); CSV views written atomically with an `_new` fallback |
| 14 | Scheduled failures looked like success; output was not logged; cp1252 console; 32 of 89 boards lived in a gitignored file | `run_fleet.ps1` never returned Python's exit code | Exit code propagated, per-run logs, UTF-8, boards moved into tracked `boards.json` |
| 15 | Misc: CSVs without BOM (garbled in Excel), Capgemini generic-search links, Deloitte appended " India" to every description, JSON-LD parser was a stub, "missing today" counted all-time, tests left 293 files in the repo, duplicate rows | - | All fixed |

### Added

- New sources: JPMorgan Chase (Oracle Recruiting Cloud), Microsoft (Eightfold), rebuilt TCS iBegin, schema.org JobPosting pages, and LinkedIn public search (opt-in, off by default).
- Scope (per user decision): BI Engineer I/II, Analytics Associate / Associate Analyst (with a data word in the title) and Market Intelligence join the main lists; Financial/FP&A, Pricing, Risk, Credit and Content Analyst roles go to `adjacent_roles_today.csv`; Senior Analyst/Associate/Executive and Assistant/Associate/Deputy Manager titles are kept only when the posting states a minimum of 3 years or less; Trainee/Apprentice/Graduate/Campus/Intern titles are excluded; Jobgether goes to `aggregator_review_today.csv`.
- Claude integration through the Claude Code CLI (your subscription login, no API key): weekly company scout and daily triage of new borderline jobs, with graceful skipping and backoff.
- Daily summary lists today's new jobs with links, split into newly posted vs newly surfaced; link canaries; board quarantine; raw dumps with offline `--replay`; `scripts/eval_classifier.py`, `scripts/smoke_sources.py`, `scripts/check_outputs.py`; GitHub Actions CI (Windows + Linux tests, gitleaks).

### Changed

- Main CSVs keep the five original columns first and append `Location, Posted, First Seen, Tier, Score, Source`.
- History lives in `outputs\state\jobfleet.sqlite`; the v2 `job_history.csv` is imported once (backed up as `job_history.v2_backup.csv`) and job keys migrate to stable ATS ids. Expect a one-time surge of "new" jobs that v2 used to miss.
- Search-based board discovery is now manual (`--discover-boards`).

### Removed

- `run_company_scout.ps1` (Codex) and `src/jobfleet/history.py` (replaced by `state.py`).

### Verification

- 168 offline unit tests; ruff clean; live smoke test passes for all 14 source types.
- Two full live runs: 83-84 boards, 0 failures, ~2.5 minutes; v2 history migrated (e.g. 25 of 32 active Amazon jobs kept their original first-seen dates); replaying the same raw dump twice yields 0 new jobs the second time.
- On 95 hand-labelled postings from a live run: 0.98 precision of listed jobs and >= 0.95 recall per family (the last few exclusion rules were informed by this same sample).
