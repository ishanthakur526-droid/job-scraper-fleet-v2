# Adding a company or a job platform

## A company on a supported platform (no code)

Most companies use one of the supported platforms. Paste the link into `my_companies.txt`, or run:

```bash
jobfleet add-company https://company.com/careers
```

It looks for a Workday, Greenhouse, Lever, Ashby, SmartRecruiters or Oracle link on the page, reads the board once, and reports how many of its open jobs are in your countries and match your profile.

To share a company with everyone, add it to `config/companies.json`:

```json
{ "company": "Example Corp", "source": "workday", "token": "example.wd1.myworkdayjobs.com|example|External" }
```

| `source` | `token` | Useful `options` |
| --- | --- | --- |
| `workday` | `host\|tenant\|site` from `https://<host>/<site>` | `max_jobs`, `search_text` |
| `greenhouse` / `lever` / `ashby` | the board name in the URL | Lever: `params` (query filters), `eu: true` |
| `smartrecruiters` | the company id in the URL | `country` (otherwise your profile's) |
| `oracle_hcm` | `host\|siteNumber` | `keywords`, `location` |
| `eightfold` | `host\|domain` | `queries`, `location` |
| `successfactors` | a search-results URL | |
| `paginated_html` | a listing URL with `{page}` or `{offset}` | |
| `generic_html` | any page with schema.org `JobPosting` data | |
| `amazon_jobs`, `accenture`, `capgemini`, `tcs_ibegin` | the search phrase, usually `{keyword}` | `max_keywords` |

`{keyword}` becomes your profile's search keywords and `{country}` its countries. Add `"countries": ["IN"]` to a country-specific careers site so other profiles skip it.

## A new platform (Python)

1. Create `src/jobfleet/sources/<platform>.py` with a `SourceAdapter` subclass:

   ```python
   class ExampleAdapter(SourceAdapter):
       name = "example"

       def list_jobs(self, board: Board) -> list[RawJob]:
           jobs = []
           for country in self.ctx.countries or ("",):        # the profile's ISO codes
               data = self.http.get_json(f"https://api.example.com/{board.token}/jobs?country={country}")
               for item in data["jobs"]:
                   if not self.time_left():                   # respect the per-company time budget
                       break
                   keep, reason = self.keep(item["title"])     # cheap title check before fetching details
                   ...
                   jobs.append(RawJob(company=board.company, title=..., location=..., url=..., description=...,
                                      source=self.name, source_id=str(item["id"]), stable_key=f"example:{item['id']}",
                                      country_codes=[...]))     # ISO codes if the API gives them
           return jobs
   ```

2. Register it in `src/jobfleet/sources/__init__.py` (`ADAPTERS`), and in `board_from_url` if its URLs are recognisable.
3. Add a test with a recorded response to `tests/test_adapters.py` (the `FakeHttp` helper in `tests/conftest.py` serves canned JSON/HTML), then check it live with `python scripts/smoke_sources.py example`.

Rules for adapters: use `self.http` (it handles retries, rate limits and secret redaction), give every job a `stable_key` that does not change between runs, never send credentials, and never try to get around CAPTCHAs or logins.
