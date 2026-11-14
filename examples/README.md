# Example Outputs

Synthetic files from the author's India analyst profile that show the shape of the outputs without committing live run data, logs or local history.

- `sample_data_bi.csv`: a family's list of every job that matches right now (one `<family>.csv` per role family, named after its `id` in profile.toml). Columns: Company, Exact Role Name, Experience Required, Application Link, System Notes, Location, Posted, First Seen, Tier, Score, Source.
- `sample_data_bi_new.csv`: the jobs that appeared since the previous run (`<family>_new.csv`).
- `sample_daily_summary_latest.md`: the run summary, including today's new jobs with links.
- `sample_source_health_latest.csv`: per-board health, including quarantined boards.

Real outputs are generated under `outputs/` and are intentionally ignored by Git.

The easiest view of a real run is `outputs/dashboard.html`; see the screenshots in `docs/images/`.
