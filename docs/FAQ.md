# Questions and answers

**Is it really free?**
Yes. JobFleet is open source (MIT), uses free public job feeds, and runs on your computer or on GitHub's free Actions. The optional Claude features use a Claude subscription you may already have, through the Claude Code CLI, with no API key and no per-use charges.

**Do I need to know programming?**
No. On Windows: double-click `Setup.bat`, answer six questions, double-click `Run.bat`. Or use [cloud mode](CLOUD.md) and only fill in a form on GitHub.

**Why do I get few results?**
Usually one of three things: the companies in the list do not hire much in your field or country (add yours to `my_companies.txt`); your level excludes most titles (for example most marketing postings are titled "Marketing *Manager*", which an early-career profile drops); or your experience range is narrow. The dashboard's *Worth a look* tab and `outputs/audit/rejected_jobs_today.csv`, which lists every rejected job with the reason, show what was left out and why.

**Why was a job I expected missing?**
Search for it in `outputs/audit/rejected_jobs_today.csv`. The `Reason` column says why: for example `excluded_seniority:lead`, `outside_your_countries`, `experience_too_high` or `weak_role_match` (title not close enough to your titles; add it to `titles`).

**A job is in the wrong country.**
Please [open an issue](https://github.com/ishanthakur526-droid/jobfleet/issues) with the exact location text. Location text is wildly inconsistent across sites, and every reported case becomes a test.

**Does it apply to jobs for me?**
No, on purpose. It finds and ranks jobs; you decide and apply on the company's own site.

**Can it search LinkedIn, Indeed or Naukri?**
LinkedIn's public search is available but off by default, because automated access is against LinkedIn's terms (`--include-linkedin`, at your own risk). Sites that require solving a CAPTCHA are not supported. JobFleet reads company career sites directly, which is where those boards get many of their postings anyway.

**How often should I run it?**
Once a day is plenty. `jobfleet schedule` sets up a weekday run on Windows; cloud mode runs on weekdays automatically.

**Where is my data?**
In the JobFleet folder (`outputs/`), or in cloud mode in your GitHub repository and its public Pages site. See [privacy in cloud mode](CLOUD.md#privacy).

**Something is broken.**
Run `jobfleet doctor`. It checks Python, the libraries, your profile, the company list, internet access, Claude and the schedule, and says what to fix.

**Can I use it for several searches?**
Yes: keep extra profiles (for example from `profiles/`) and run `jobfleet run --profile profiles/other.toml --output-dir outputs_other`.
