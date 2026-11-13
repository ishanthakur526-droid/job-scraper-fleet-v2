# Make JobFleet yours

Everything about your search lives in **`profile.toml`** in the JobFleet folder (in cloud mode: in your GitHub repository). It is a plain text file. Open it with Notepad, TextEdit or GitHub's pencil icon, change a line, save, and run again.

> Not comfortable editing? Run `Setup.bat` (or `jobfleet setup`) again and answer the questions. Your old profile is kept as `profile.backup.toml`.

If a value is wrong, JobFleet stops before searching and says exactly what to fix, for example:

```
profile.toml needs a fix:
- [location] 'Inda' is not a country I know. Did you mean 'India'?
```

## 1. Where: `[location]`

```toml
[location]
countries = ["India"]              # one or more: ["United States", "Canada"]
cities    = []                     # optional: ["Bengaluru", "Pune"]
remote    = "include"              # include | only | exclude
```

- **countries**: English names ("Germany", "United Kingdom"), common short forms ("USA", "UK", "UAE") or two-letter codes ("DE").
- **cities**: leave empty for the whole country. Old and new names both work ("Bangalore" = "Bengaluru", "Gurgaon" = "Gurugram"). You can also use a state or area ("Karnataka", "Bay Area").
- **remote**:
  - `include`: remote jobs in your countries count too (default).
  - `only`: only remote jobs. With `only` you may leave `countries` empty to accept remote jobs from anywhere.
  - `exclude`: no fully remote jobs. Hybrid jobs with an office in your country stay.

## 2. Level: `[experience]`

```toml
[experience]
min_years = 0
max_years = 3
level     = "early_career"
```

**`min_years` / `max_years`** is the experience range you are looking for. JobFleet reads each posting's requirement:

| Posting says | With 0-3 years | With 5-10 years |
| --- | --- | --- |
| "2-5 years of experience" | kept (overlaps) | kept (overlaps) |
| "1-3 years of experience" | kept | dropped (too junior) |
| "minimum 4 years" | dropped | kept |
| "3+ years" | kept | kept |
| "0-2 years" / "freshers welcome" | kept | dropped (too junior) |
| nothing stated | kept | kept |
| "5+ years preferred" (only preferred) | kept, noted | kept |

Company facts ("over 45 years of excellence"), ages and contract lengths are ignored. If a posting contradicts itself (for example "1-3 years" and "5+ years"), the job is kept and labelled *Needs review*.

**`level`** decides how job-title words such as *Senior* or *Manager* are treated:

| Title word | student | early_career | mid | senior | leadership |
| --- | --- | --- | --- | --- | --- |
| Intern, Internship | ✔ | ✘ | ✘ | ✘ | ✘ |
| Trainee, Graduate, Campus, Apprentice | ✔ | ✔ | ✘ | ✘ | ✘ |
| Junior | ✔ | ✔ | ✔ | ✘ | ✘ |
| Assistant/Associate/Deputy Manager | ✘ | ? | ✔ | ✔ | ✘ |
| Senior | ✘ | ? | ✔ | ✔ | ✔ |
| Lead, Staff | ✘ | ✘ | ? | ✔ | ✔ |
| Manager, Architect | ✘ | ✘ | ✘ | ✔ | ✔ |
| Principal | ✘ | ✘ | ✘ | ✔ | ✔ |
| Head, Director | ✘ | ✘ | ✘ | ? | ✔ |
| VP, Chief | ✘ | ✘ | ✘ | ✘ | ✔ |
| Level III and up ("Analyst III") | ✘ | ? | ✔ | ✔ | ✔ |

✔ allowed · ✘ dropped · **?** kept only if the posting states a minimum inside your range (labelled *Needs review*).

A word that is part of one of **your own titles** never counts against a job: with "Product Manager" in your titles, product manager jobs are kept even at the early-career level.

## 3. What: `[[role_family]]`

Each `[[role_family]]` block is one kind of job with its own dashboard tab and CSV file. Add as many as you like.

```toml
[[role_family]]
id     = "data_engineering"            # short name, used for file names (optional)
name   = "Data Engineering"             # shown on the dashboard
titles = ["Data Engineer", "Analytics Engineer", "ETL Developer"]
title_keywords = ["etl", "data pipeline"]          # optional: weaker match on these title words
keywords = ["sql", "python", "spark", "airflow"]    # optional: description words that raise the score
exclude_title_words = ["intern"]                    # optional: never put titles with these words here
domains = ["engineering"]                           # optional: job areas this family covers (see below)
```

- **titles**: the core of the matching. Word order and small differences do not matter: "Analyst, Data", "Data Analyst II" and "Sr. Data Analyst" all match "Data Analyst" (seniority is checked separately).
- **keywords**: each one found in the description adds points (up to a limit). A title match plus a few keywords means *High confidence*.
- **domains**: to keep lists clean, JobFleet drops whole job areas that rarely fit, unless one of your families covers them: `engineering`, `data_science_ml`, `security`, `it_operations`, `it_systems`, `qa_testing`, `design`, `content`, `sales`, `customer_support`, `recruiting`, `hr`, `legal`, `martech`, `non_office` (healthcare, trades, teaching). The ready-made families already list theirs.

### Ready-made families

`jobfleet setup` offers these, each with titles, keywords and domains filled in (see `src/jobfleet/role_library.py`):

Software Engineering · DevOps & Cloud · Data Engineering · Data Science & ML · Data & BI Analytics · Research & Insights · Excel / MIS Reporting · Product Management · Project & Program Management · Design (UX/UI) · QA & Testing · Cybersecurity · IT Support & Systems · Marketing · Sales & Business Development · Customer Success & Support · HR & Recruiting · Finance & Accounting · Operations & Supply Chain · Content & Writing · Legal & Compliance

### A second-tier list: `[adjacent]`

Roles that are related but not your first choice go to a separate *Related roles* tab:

```toml
[adjacent]
titles = ["Financial Analyst", "Pricing Analyst"]
```

## 4. Companies

- **`my_companies.txt`**: paste career-page or job-board links, one per line. Optionally put a name first: `Airbnb | https://boards.greenhouse.io/airbnb`.
- **`jobfleet add-company https://company.com/careers`** finds the job board behind a careers page, checks how many matching jobs it has today, and saves it.
- **`config/companies.json`**: the shared list. `{keyword}` in an entry is replaced by your search keywords and `{country}` by your countries; `"countries": ["IN"]` limits a country-specific careers site to profiles that include India.

## 5. Search words: `[search]`

Some career sites (Amazon, Accenture, Capgemini, EY, Microsoft, JPMorgan, TCS) need a search phrase. JobFleet uses `[search] keywords`, or the first titles of your families if you leave it out:

```toml
[search]
keywords = ["data engineer", "analytics engineer", "etl developer"]
```

## 6. Claude: `[ai]`

```toml
[ai]
enabled = true          # false = never call Claude
model   = "sonnet"

[ai.scout]              # weekly company search
every_days = 7

[ai.triage]             # daily second opinion on borderline jobs
max_items          = 60
promote_confidence = 0.75   # how sure Claude must be to add a "Worth a look" job to your list
demote_confidence  = 0.85   # how sure Claude must be to take a job off your list
```

## 7. Advanced: `[advanced]`

Everything here is optional.

```toml
[advanced]
exclude_levels     = ["lead"]              # drop these title words regardless of the level preset
allow_levels       = ["manager"]           # always allow these
conditional_levels = ["senior"]            # keep only when the posting's range fits
senior_only_for    = ["analyst", "associate"]   # "Senior" allowed only in these titles
allow_domains      = ["sales"]             # keep a job area without making a family for it
exclude_domains    = ["design", "legal"]   # replace the automatic list entirely
tie_priority       = ["research", "data_bi"]    # which family wins when a job fits two equally
prefilter_terms    = ["analyst", "data"]   # title words worth opening the full posting for
possible_terms     = ["analyst"]           # title words that make a weak match "Worth a look"

[advanced.title_abbreviations]             # expanded in titles before matching
bi  = "business intelligence"
sde = "software development engineer"
```

Level names: `intern`, `entry_program`, `junior`, `junior_manager`, `senior`, `vp`, `director`, `chief`, `principal`, `head`, `architect`, `lead`, `staff`, `manager`, `level_3_plus`.

## Examples

The [`profiles/`](../profiles) folder has complete examples to copy over `profile.toml`:

| File | Search |
| --- | --- |
| `us-software-engineer-mid.toml` | United States, software engineering, 3-7 years |
| `uk-marketing-early-career.toml` | United Kingdom, marketing, 0-3 years |
| `germany-data-scientist-senior.toml` | Germany, data science + data engineering, 5-15 years |
| `singapore-finance.toml` | Singapore, finance & accounting, 0-4 years |
| `canada-customer-success.toml` | Canada, customer success + sales, 2-6 years |
| `remote-product-manager.toml` | Remote only (US, UK, Ireland), product management |
| `india-software-engineer-fresher.toml` | India, software + QA, 0-2 years |
| `india-analyst-early-career.toml` | The author's own search: India, three analyst families, 0-3 years, with every rule spelled out |
