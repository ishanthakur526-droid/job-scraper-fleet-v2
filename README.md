# Job Scraper Fleet v2

Job Scraper Fleet v2 is a local, no-cost workflow for finding India-focused early-career job listings across three target families:

- Data & BI
- Research
- Excel / MIS

It checks configured company career boards and public ATS endpoints, applies deterministic guardrails, removes cross-category duplicates, tracks what has already been seen, and writes daily CSV files for applications.

## Why This Project Exists

The goal is to turn a repetitive job-search process into a repeatable data pipeline:

- collect listings from supported public career sources
- normalize messy job data into consistent CSVs
- filter for India-focused early-career analyst roles
- separate fresh listings from already-seen jobs
- keep audit, health, and false-negative review files for quality control
- run automatically on weekdays through Windows Task Scheduler

The core scraper is deterministic and testable. The optional Codex CLI company scout only proposes new company candidates; deterministic verification decides whether any source is safe enough to add.

## Daily Files To Check

After the weekday 4 PM run completes, start in:

```text
outputs
```

Check these first. They are the daily action files:

```text
new_only_data_bi_roles_today.csv
new_only_research_roles_today.csv
new_only_excel_sheets_roles_today.csv
```

These contain only jobs that were newly detected compared with the local history from earlier runs.

Then check the full current pools:

```text
data_bi_roles_today.csv
research_roles_today.csv
excel_sheets_roles_today.csv
```

These are rebuilt fresh every run and contain the best currently live matches found that day. They can include jobs that were seen before and are still active.

Also check the latest summary:

```text
reports\daily_summary_latest.md
```

If you have extra time, review borderline matches in:

```text
quality_tiers\possible_match_data_bi_roles_today.csv
quality_tiers\possible_match_research_roles_today.csv
quality_tiers\possible_match_excel_sheets_roles_today.csv
```

If a CSV is open in Excel during a run, the exporter may write a fallback file with `_new` in the filename. Close the open CSV and use the newest file by modified time.

## How A Run Works

Each run follows this flow:

1. Optionally runs the company scout to propose more medium-to-large India-hiring companies.
2. Verifies scout candidates deterministically before adding supported boards to `config\discovered_boards.json`.
3. Runs lightweight board discovery for supported public ATS/career sources.
4. Scrapes configured and discovered boards through structured adapters.
5. Normalizes company, title, location, application URL, description, source, and posting metadata.
6. Filters to India-relevant roles.
7. Applies the experience rule for early-career roles, including overlapping ranges like `2-5 years`.
8. Excludes seniority-heavy roles such as senior manager, lead, principal, staff, director, AVP, DVP, and VP.
9. Scores jobs against the three role families.
10. Assigns each accepted job to only one best-fit category so the same URL does not appear twice across category CSVs.
11. Writes current jobs, new-only jobs, quality-tier files, audit files, health reports, and run summaries.
12. Updates local history so future runs know what is new, still active, or missing.

If the company scout fails, the main deterministic scraper still continues with the existing configured boards.
Older scout output is not re-used automatically after a failed scout run; only a candidate file refreshed during the current run is passed into verification.

## Manual Run

From this folder:

```powershell
.\run_fleet.ps1
```

From the repository root:

```powershell
.\job_scraper_fleet_v2\run_fleet.ps1
```

Useful options:

```powershell
.\run_fleet.ps1 -SkipCompanyScout
.\run_fleet.ps1 -SkipDiscoverBoards
.\run_fleet.ps1 -IncludeSearch
.\run_fleet.ps1 -MaxPerCategory 50
```

The normal scheduled process uses `run_fleet.ps1`.
By default, the workflow writes up to 40 accepted jobs per category. You can raise or lower this with `-MaxPerCategory`.

## Daily Schedule

The scheduled task name is:

```text
Job Scraper Fleet v2 - Weekday 4PM
```

Schedule:

```text
Monday-Friday at 4:00 PM
```

The task uses Windows Task Scheduler's `StartWhenAvailable` setting. If the laptop is off or unavailable at 4 PM, Windows should run the missed task soon after the machine becomes available and you log in.

Install or update the scheduled task:

```powershell
.\install_scheduled_task.ps1
```

Check the scheduled task:

```powershell
.\check_scheduled_task.ps1
```

Remove the scheduled task:

```powershell
.\uninstall_scheduled_task.ps1
```

Keep the laptop connected to the internet. The task waits for network availability and ignores overlapping runs.

## Main Outputs

Current best matches:

```text
outputs\data_bi_roles_today.csv
outputs\research_roles_today.csv
outputs\excel_sheets_roles_today.csv
```

New listings only:

```text
outputs\new_only_data_bi_roles_today.csv
outputs\new_only_research_roles_today.csv
outputs\new_only_excel_sheets_roles_today.csv
```

Quality tiers:

```text
outputs\quality_tiers\high_confidence_*
outputs\quality_tiers\needs_review_*
outputs\quality_tiers\possible_match_*
```

Use `high_confidence_*` for the cleanest application shortlist. Use `needs_review_*` for plausible matches that may need a quick human scan. Use `possible_match_*` occasionally to catch false negatives that strict matching may have excluded from the main CSVs.

## Audit And Health Files

Audit files beside the main CSVs:

```text
outputs\audit_data_bi_roles_today.csv
outputs\audit_research_roles_today.csv
outputs\audit_excel_sheets_roles_today.csv
```

These include score, source, location, matched terms, category, and retrieval time. They are mainly for debugging and understanding why a job was included.

Rejected-job audit:

```text
outputs\audit\rejected_jobs_today.csv
```

This lists collected jobs that did not enter the main CSVs, with a best category guess and rejection reason.

Source health:

```text
outputs\health\source_health_latest.csv
```

This shows which boards worked, which returned no jobs, and which failed. Check this when the daily counts look unusually low.

Run logs and summary:

```text
outputs\logs\run_*.json
outputs\reports\daily_summary_latest.md
```

## History And Expired Jobs

Persistent history is stored in:

```text
outputs\state\job_history.csv
```

This tracks each seen job with active/missing status, first seen time, last seen time, seen count, and missing count.

Jobs that were seen before but are not returned by the latest live run are written to:

```text
outputs\state\expired_or_missing_jobs.csv
```

The `*_roles_today.csv` files are not an archive. They are fresh snapshots from the latest run. If a job disappears from its source board, it drops out of the current CSV and is tracked as missing.

To intentionally reset history, delete:

```text
outputs\state\job_history.csv
```

The next run will treat all currently found jobs as new.

## Configuration

Role categories and guardrails:

```text
config\categories.json
```

Curated static boards:

```text
config\boards.json
```

Automatically discovered boards:

```text
config\discovered_boards.json
```

This file is generated locally and ignored by Git. A template is included at:

```text
config\discovered_boards.example.json
```

Board discovery settings:

```text
config\discovery.json
```

Company scout prompt and output schema:

```text
config\company_scout_prompt.md
config\company_scout_schema.json
```

Manual boards stay in `boards.json`; generated boards stay in `discovered_boards.json` so the curated registry remains clean.

## Supported Sources

The workflow currently supports:

- Lever
- Greenhouse
- Ashby
- SmartRecruiters
- Workday
- SuccessFactors-style career pages
- Amazon Jobs public search JSON
- Accenture public careers search API
- Capgemini public jobstream API
- TCS iBegin public search endpoint
- Selected vetted paginated HTML career pages, such as Deloitte and Cognizant
- Generic HTML detail extraction for discovered direct job URLs

Large companies with custom or protected career systems need a dedicated adapter before they can be considered reliable enough for daily use.

## Company Scout And Board Discovery

The company scout is run by:

```powershell
.\run_company_scout.ps1
```

It uses your local Codex CLI to research companies that may be hiring in India for the target role families. Its output is written to:

```text
outputs\research\company_candidates_latest.json
```

The scout does not directly modify the main board list. The Python verifier checks whether a candidate has a supported, working, India-relevant ATS/career source with at least one category-relevant India job before promoting it to:

```text
config\discovered_boards.json
```

Verification results:

```text
outputs\health\company_candidate_verification_latest.csv
```

Board discovery is controlled by `config\discovery.json` and is enabled by default. It runs small free web searches, extracts supported board URLs, validates them, and saves only boards with India-relevant category matches. Reports are written to:

```text
outputs\health\board_discovery_latest.csv
```

## Tests And Sanity Checks

Run the unit test suite from the project folder:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src)
python -m unittest discover -s tests
```

Check JSON config validity:

```powershell
python -m json.tool config\boards.json
python -m json.tool config\categories.json
python -m json.tool config\discovery.json
```

Compile-check the Python code:

```powershell
python -m compileall -q src tests
```

## Repository Hygiene

Live outputs are intentionally not committed. The repository keeps source code, tests, configuration, scripts, documentation, and small synthetic examples.

Ignored local/generated paths include:

```text
outputs/
outputs_search/
.test_tmp/
config/discovered_boards.json
__pycache__/
*.pyc
```

Example output shapes are available in:

```text
examples/
```

## Current Sanity Status

The latest sanity pass confirmed:

- `31/31` unit tests passing.
- JSON configuration files parse successfully.
- Python source and tests compile successfully.
- All configured boards have a registered adapter.
- Auto-discovered boards must return at least one India-relevant category hit before being saved.
