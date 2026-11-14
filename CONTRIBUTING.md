# Contributing

Thanks for helping. The most useful contributions are small and come with evidence:

- **A wrong decision** (job in the wrong country, wrong level, missed job): open an issue with the job title, location text and, if possible, the line from `outputs/audit/rejected_jobs.csv`. Every fixed case becomes a test.
- **A company that should be included**: open an issue or a pull request adding it to `config/companies.json` ([how](docs/ADD_A_SOURCE.md)).
- **A new job platform or role family**: open an issue first so we can agree on the approach.

## Development setup

```bash
uv sync                              # Python 3.11+
uv run pytest -q                     # must pass, offline
uv run ruff check src tests scripts  # must be clean
```

## Ground rules

- **Behaviour changes need proof.** If you change classification rules, replay a saved run before and after (`scripts/compare_runs.py`) and describe the differences in the pull request.
- **Be polite to websites.** Use the shared `HttpClient` (rate limits, retries, back-off). No scraping behind logins, no CAPTCHA solving, no ignoring of a site's blocking.
- **No secrets in code, tests or fixtures.** CI runs a secret scan on every push.
- Keep user-facing text plain: the README and error messages are read by people who do not program.
