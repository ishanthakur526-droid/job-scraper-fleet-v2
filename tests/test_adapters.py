import json

from conftest import FakeHttp
from jobfleet.geo import resolve
from jobfleet.models import Board, legacy_url_key
from jobfleet.sources import AdapterContext, adapter_for, board_from_url
from jobfleet.sources.html_pages import find_job_posting, job_from_jsonld
from jobfleet.sources.linkedin_guest import parse_detail, parse_search_cards
from jobfleet.sources.workday import INDIA_COUNTRY_ID, find_india_facet

KEEP_ANALYSTS = AdapterContext(prefilter=lambda title, flags=None: ("analyst" in title.lower(), "irrelevant_title"))


def test_amazon_uses_public_job_path_and_keeps_uuid_as_legacy_key():
    url0 = "https://www.amazon.jobs/en/search.json?base_query=analyst&country=IND&offset=0&result_limit=100"
    item = {
        "id": "cb6affc4-b34f-49c9-ba58-e8aa43e1afc5",
        "id_icims": "10593289",
        "job_path": "/en/jobs/10593289/business-analyst-payments",
        "title": "Business Analyst - Payments",
        "normalized_location": "Bengaluru, Karnataka, IND",
        "country_code": "IND",
        "locations": [json.dumps({"normalizedLocation": "Bengaluru, Karnataka, IND", "countryIso2a": "IN"})],
        "description": "Own payments dashboards.",
        "basic_qualifications": "- 1+ years of experience in analytics",
        "preferred_qualifications": "- 5+ years of experience in payments",
        "posted_date": "September 18, 2026",
    }
    http = FakeHttp(json_data={url0: {"hits": 1, "jobs": [item]}})
    jobs = adapter_for("amazon_jobs", http).list_jobs(Board("Amazon", "amazon_jobs", "analyst"))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.url == "https://www.amazon.jobs/en/jobs/10593289/business-analyst-payments"
    assert job.key() == "amazon_jobs:10593289"
    assert legacy_url_key("https://www.amazon.jobs/en/jobs/cb6affc4-b34f-49c9-ba58-e8aa43e1afc5") in job.all_legacy_keys()
    assert "1+ years" in job.requirements_text and "5+ years" in job.preferred_text
    assert "IN" in job.country_codes and job.posted_date == "2026-09-18"


def test_smartrecruiters_filters_india_and_pages_past_100():
    base = "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings"
    page1 = [{"id": f"{i}", "name": "Data Analyst" if i == 0 else "Welder", "location": {"city": "Pune", "country": "in", "fullLocation": "Pune, MH, India"}} for i in range(100)]
    page2 = [{"id": "100", "name": "MIS Analyst", "location": {"city": "Bengaluru", "country": "in"}}]
    http = FakeHttp(
        json_data={
            f"{base}?country=in&limit=100&offset=0": {"totalFound": 101, "content": page1},
            f"{base}?country=in&limit=100&offset=100": {"totalFound": 101, "content": page2},
            f"{base}/0": {"postingUrl": "https://jobs.smartrecruiters.com/BoschGroup/0-data-analyst", "jobAd": {"sections": {"jobDescription": {"text": "<p>SQL</p>"}}}},
            f"{base}/100": {"jobAd": {"sections": {}}},
        }
    )
    jobs = adapter_for("smartrecruiters", http, KEEP_ANALYSTS).list_jobs(Board("Bosch", "smartrecruiters", "BoschGroup"))
    assert len(jobs) == 101
    detail_calls = [url for _m, url, _p in http.calls if url.startswith(f"{base}/")]
    assert detail_calls == [f"{base}/0", f"{base}/100"]  # details only for prefilter-kept titles
    assert jobs[0].url.endswith("0-data-analyst") and jobs[0].country_codes == ["in"]
    assert jobs[1].flags.get("prefilter") == "irrelevant_title"


def _workday_facets():
    return [
        {"facetParameter": "jobFamilyGroup", "values": [{"descriptor": "Finance", "id": "x1", "count": 3}]},
        {
            "facetParameter": "locationMainGroup",
            "values": [
                {"facetParameter": "locationCountry", "values": [{"descriptor": "India", "id": INDIA_COUNTRY_ID, "count": 3}]},
                {"facetParameter": "locations", "values": [{"descriptor": "Remote - Indiana", "id": "ind-us", "count": 6}]},
            ],
        },
    ]


def test_workday_finds_nested_and_custom_india_facets():
    assert find_india_facet(_workday_facets()) == ("locationCountry", [INDIA_COUNTRY_ID], "country")
    custom = [{"facetParameter": "CF_-_REC_-_LRV_Country", "values": [{"descriptor": "India", "id": "abc", "count": 9}]}]
    assert find_india_facet(custom) == ("CF_-_REC_-_LRV_Country", ["abc"], "country")
    locations_only = [{"facetParameter": "locations", "values": [{"descriptor": "Bangalore", "id": "b1"}, {"descriptor": "Remote - Indiana", "id": "i1"}]}]
    assert find_india_facet(locations_only) == ("locations", ["b1"], "locations")


def test_workday_pages_with_india_facet_and_fetches_detail_for_n_locations():
    host, tenant, site = "gartner.wd5.myworkdayjobs.com", "gartner", "EXT"
    endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    postings = [
        {"title": "Business Analyst", "externalPath": "/job/2-Locations/Business-Analyst_R1", "locationsText": "2 Locations"},
        {"title": "Senior Director", "externalPath": "/job/Gurgaon/Senior-Director_R2", "locationsText": "Gurgaon"},
    ] + [{"title": f"Analyst {i}", "externalPath": f"/job/Pune/Analyst_{i}", "locationsText": "Pune"} for i in range(20)]

    def respond(payload):
        assert payload["limit"] == 20  # Workday returns HTTP 400 above 20
        if not payload["appliedFacets"]:
            return {"total": 900, "facets": _workday_facets(), "jobPostings": []}
        assert payload["appliedFacets"] == {"locationCountry": [INDIA_COUNTRY_ID]}
        start = payload["offset"]
        total = 22 if start == 0 else 0  # later pages report total 0
        return {"total": total, "jobPostings": postings[start : start + 20]}

    detail = {"jobPostingInfo": {"title": "Business Analyst", "location": "Gurgaon", "additionalLocations": ["Bengaluru"], "country": {"descriptor": "India"}, "jobReqId": "R1", "externalUrl": f"https://{host}/EXT/job/Gurgaon/Business-Analyst_R1", "jobDescription": "<p>2-4 years of experience</p>", "startDate": "2026-11-10"}}
    http = FakeHttp(post={endpoint: respond}, json_data={f"https://{host}/wday/cxs/{tenant}/{site}/job/2-Locations/Business-Analyst_R1": detail, f"https://{host}/wday/cxs/{tenant}/{site}/job/Pune/*": {"jobPostingInfo": {}}})
    context = AdapterContext(prefilter=lambda title, flags=None: ("director" not in title.lower(), "excluded_seniority"))
    jobs = adapter_for("workday", http, context).list_jobs(Board("Gartner", "workday", f"{host}|{tenant}|{site}"))
    assert len(jobs) == 22
    first = jobs[0]
    assert first.key() == "workday:gartner:r1"
    assert first.url == detail["jobPostingInfo"]["externalUrl"]
    assert first.locations == ["Bengaluru"] and first.country_codes == ["India"]
    assert legacy_url_key(f"https://{host}/en-US/{site}/job/2-Locations/Business-Analyst_R1") in first.all_legacy_keys()
    assert jobs[1].flags.get("prefilter") == "excluded_seniority"


def test_lever_includes_requirement_lists_and_country():
    http = FakeHttp(json_data={"https://api.lever.co/v0/postings/fampay?mode=json": [{
        "id": "abc", "text": "Data Analyst", "country": "IN", "createdAt": 1762000000000,
        "categories": {"location": "Bengaluru", "allLocations": ["Bengaluru", "Remote"]},
        "descriptionPlain": "About the role", "lists": [{"text": "Requirements", "content": "<li>2+ years of experience with SQL</li>"}],
        "hostedUrl": "https://jobs.lever.co/fampay/abc",
    }]})
    job = adapter_for("lever", http).list_jobs(Board("Fam", "lever", "fampay"))[0]
    assert "2+ years of experience with SQL" in job.description
    assert job.country_codes == ["IN"] and job.locations == ["Bengaluru", "Remote"] and job.url_kind == "api"


def test_ashby_and_greenhouse_structured_locations():
    ashby = FakeHttp(json_data={"https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=false": {"jobs": [{
        "id": "1", "title": "Data Analyst", "location": "New York", "jobUrl": "https://jobs.ashbyhq.com/acme/1",
        "address": {"postalAddress": {"addressCountry": "United States"}},
        "secondaryLocations": [{"location": "Bengaluru", "address": {"postalAddress": {"addressCountry": "India"}}}],
    }]}})
    job = adapter_for("ashby", ashby).list_jobs(Board("Acme", "ashby", "acme"))[0]
    assert job.country_codes == ["United States", "India"] and job.locations == ["Bengaluru"]
    greenhouse = FakeHttp(json_data={"https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true": {"jobs": [{
        "id": 7, "title": "Analyst", "location": {"name": "Remote"}, "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/7",
        "offices": [{"name": "Pune", "location": "Pune, Maharashtra, India"}], "content": "&lt;p&gt;SQL&lt;/p&gt;", "first_published": "2026-11-12T09:28:57-05:00",
    }]}})
    gh = adapter_for("greenhouse", greenhouse).list_jobs(Board("Acme", "greenhouse", "acme"))[0]
    assert gh.locations == ["Pune, Maharashtra, India"] and gh.description == "SQL" and gh.posted_date == "2026-11-12"


def test_capgemini_links_use_the_country_job_page():
    # 2026-11-14: the feed's apply_job_url (careers.capgemini.com/job/...) returned 404 for every country.
    url = "https://cg-jobstream-api.azurewebsites.net/api/job-search?page=1&size=50&country_code={site}&search=analyst"
    http = FakeHttp(json_data={
        url.format(site="in-en"): {"data": [
            {"id": "427805-en_GB_SAPBTP", "title": "Business Analyst", "location": "Pune", "apply_job_url": "https://careers.capgemini.com/job/a/1/"},
            {"id": "", "title": "No id", "location": "Pune"},
        ]},
        url.format(site="in-en").replace("page=1", "page=2"): {"data": []},
        url.format(site="us-en"): {"data": [{"id": "9-en_US_SAPBTP", "title": "Data Analyst", "location": "Atlanta"}]},
        url.format(site="us-en").replace("page=1", "page=2"): {"data": []},
    })
    india = adapter_for("capgemini", http).list_jobs(Board("Capgemini", "capgemini", "analyst"))
    assert [j.url for j in india] == ["https://www.capgemini.com/in-en/jobs/427805-en_GB_SAPBTP/"]
    assert india[0].legacy_keys == ["https://careers.capgemini.com/job/a/1"] and india[0].key() == "capgemini:427805-en_gb_sapbtp"
    us = adapter_for("capgemini", http, AdapterContext(countries=("US", "BR"))).list_jobs(Board("Capgemini", "capgemini", "analyst"))
    assert [j.url for j in us] == ["https://www.capgemini.com/us-en/jobs/9-en_US_SAPBTP/"]


def test_deloitte_listing_no_longer_fakes_india_in_description():
    token = "https://apply.deloitte.com/en_US/careers/SearchJobs/India/?jobRecordsPerPage=10&jobOffset={offset}"
    page0 = token.replace("{offset}", "0")
    http = FakeHttp(text={
        page0: '<li><a href="/en_US/careers/JobDetail/Data-Analyst/123">Data Analyst</a><p>Multiple Locations</p></li>'
               '<li><a href="/en_US/careers/JobDetail/Manager/124">Manager</a><p>Indianapolis, Indiana, United States</p></li>',
        token.replace("{offset}", "10"): "",
    })
    jobs = adapter_for("paginated_html", http).list_jobs(Board("Deloitte", "paginated_html", token))
    assert "India" not in jobs[0].description
    assert jobs[0].flags.get("geo_hint") == "target" and jobs[0].location == ""
    assert resolve(jobs[1].location).status == "foreign"  # Indianapolis row is not hinted as India
    assert "geo_hint" not in jobs[1].flags


def test_successfactors_listing_and_detail():
    listing = "https://careers.example.com/search/?q=analyst&locationsearch=India"
    detail = "https://careers.example.com/job/Bengaluru-Data-Analyst-KA/123/"
    http = FakeHttp(text={
        listing: f'<table><tr><td><a href="{detail}">Data Analyst</a></td><td>Bengaluru, KA, IN</td></tr></table>',
        f"{listing}&startrow=25": "<table></table>",
        detail: "<h1>Data Analyst</h1><p>Location: Bengaluru, KA, IN</p><p>Date: Apr 28, 2026</p><p>SQL and Power BI. 1-3 years experience.</p>",
    })
    job = adapter_for("successfactors", http).list_jobs(Board("Example", "successfactors", listing))[0]
    assert job.title == "Data Analyst" and job.location == "Bengaluru, KA, IN" and job.source_id == "123"
    assert job.posted_date == "2026-04-28" and "Power BI" in job.description


def test_accenture_mapping():
    http = FakeHttp(post={"https://www.accenture.com/api/accenture/elastic/findjobs": {"data": [{
        "requisitionId": "ATCI-123", "title": "Business Data Analyst", "location": ["Bengaluru"],
        "jobDetailUrl": "https://www.accenture.com/{0}/careers/jobdetails?id=ATCI-123", "jobDescriptionClean": "Dashboards.",
        "mustHaveSkills": ["Power BI", "SQL"], "yearsOfExperience": "3 to 5 years",
    }]}})
    board = Board("Accenture", "accenture", "analyst", options={"pages": 1})
    job = adapter_for("accenture", http).list_jobs(board)[0]
    assert job.url == "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-123"
    assert "Experience: 3 to 5 years" in job.description and job.location == "Bengaluru"


def test_oracle_hcm_keeps_finder_separators_unencoded():
    host = "jpmc.fa.oraclecloud.com"
    req = {"Id": "210808661", "Title": "Fund Servicing Analyst", "PrimaryLocation": "Mumbai, Maharashtra, India", "PrimaryLocationCountry": "IN", "PostedDate": "2026-11-12"}
    http = FakeHttp(json_data={
        f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?*": {"items": [{"TotalJobsCount": 1, "requisitionList": [req]}]},
        f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?*": {"items": [{"ExternalQualificationsStr": "<p>0-2 years of experience</p>"}]},
    })
    job = adapter_for("oracle_hcm", http, KEEP_ANALYSTS).list_jobs(Board("JPMorgan Chase", "oracle_hcm", f"{host}|CX_1001"))[0]
    list_url = http.calls[0][1]
    assert "finder=findReqs;siteNumber=CX_1001,facetsList=LOCATIONS,limit=25,offset=0," in list_url
    assert job.url == f"https://{host}/hcmUI/CandidateExperience/en/sites/CX_1001/job/210808661"
    assert job.country_codes == ["IN"] and "0-2 years" in job.requirements_text


def test_eightfold_uses_position_url():
    host = "apply.careers.microsoft.com"
    http = FakeHttp(json_data={
        f"https://{host}/api/pcsx/search?*": {"data": {"positions": [{"id": 77, "displayJobId": "2000", "name": "Data Analyst", "locations": ["India, Telangana, Hyderabad"], "positionUrl": "/careers/job/77", "postedTs": 1786088368}]}},
        f"https://{host}/api/pcsx/position_details?*": {"data": {"jobDescription": "<p>SQL</p>"}},
    })
    board = Board("Microsoft", "eightfold", f"{host}|microsoft.com", options={"queries": ["data analyst"], "pages": 1})
    job = adapter_for("eightfold", http, KEEP_ANALYSTS).list_jobs(board)[0]
    assert job.url == f"https://{host}/careers/job/77" and job.description == "SQL"


def test_generic_jsonld_job_posting():
    html = """<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Organization"},
      {"@type":"JobPosting","title":"MIS Executive","hiringOrganization":{"name":"Acme"},
       "jobLocation":{"@type":"Place","address":{"addressLocality":"Pune","addressCountry":"IN"}},
       "description":"<p>Advanced Excel</p>","datePosted":"2026-11-01","experienceRequirements":{"monthsOfExperience":24}}]}</script>"""
    job = job_from_jsonld(find_job_posting(html), "https://acme.example/jobs/1")
    assert job.title == "MIS Executive" and job.company == "Acme" and job.country_codes == ["IN"]
    assert "24 months of experience" in job.description and job.posted_date == "2026-11-01"


def test_linkedin_card_and_detail_parsing():
    cards = parse_search_cards(
        '<li><div class="base-card" data-entity-urn="urn:li:jobPosting:4446587231">'
        '<a class="base-card__full-link" href="https://in.linkedin.com/jobs/view/x-4446587231?trk=a"></a>'
        '<h3 class="base-search-card__title"> Data Analyst </h3><h4 class="base-search-card__subtitle"><a>EXL</a></h4>'
        '<span class="job-search-card__location">Gurugram, Haryana, India</span><time datetime="2026-11-12"></time></div></li>'
    )
    assert cards == [{"job_id": "4446587231", "title": "Data Analyst", "company": "EXL", "location": "Gurugram, Haryana, India", "posted": "2026-11-12"}]
    description, seniority = parse_detail(
        '<div class="show-more-less-html__markup"><p>1-3 years</p></div>'
        '<li class="description__job-criteria-item"><h3>Seniority level</h3><span>Entry level</span></li>'
    )
    assert description == "1-3 years" and seniority == "Entry level"


def test_board_from_url_recognises_supported_sources():
    assert board_from_url("https://jobs.lever.co/example/abc").token == "example"
    assert board_from_url("https://job-boards.greenhouse.io/example/jobs/123").token == "example"
    assert board_from_url("https://boards.greenhouse.io/embed/job_board?for=acme").token == "acme"
    assert board_from_url("https://jobs.ashbyhq.com/example/abc").token == "example"
    assert board_from_url("https://careers.smartrecruiters.com/Freshworks").token == "Freshworks"
    assert board_from_url("https://workday.wd5.myworkdayjobs.com/en-US/Workday").token == "workday.wd5.myworkdayjobs.com|workday|Workday"
    assert board_from_url("https://gartner.wd5.myworkdayjobs.com/EXT/job/x").token == "gartner.wd5.myworkdayjobs.com|gartner|EXT"
    assert board_from_url("https://wd1.myworkdaysite.com/recruiting/wf/WellsFargoJobs").token == "wd1.myworkdaysite.com|wf|WellsFargoJobs"
    assert board_from_url("https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/1").token == "jpmc.fa.oraclecloud.com|CX_1001"
    assert board_from_url("https://careers.ey.com/ey/job/x").source == "successfactors"
    assert board_from_url("https://example.com/careers") is None


def test_workday_does_not_trust_india_filter_for_foreign_rows_and_uses_path_location():
    from jobfleet.sources.workday import WorkdayAdapter, _location_from_path

    assert _location_from_path("/job/Bengaluru-BDC9A/Procure-to-Pay_AIOC-1") == "Bengaluru BDC9A"
    assert _location_from_path("/job/India---Bangalore/X_JR1") == "India - Bangalore"
    assert _location_from_path("/job/2-Locations/X_R1") == ""
    adapter = WorkdayAdapter(FakeHttp(), AdapterContext(prefilter=lambda t, f=None: (False, "skip")))
    board = Board("LSEG", "workday", "lseg.wd3.myworkdayjobs.com|lseg|Careers")
    foreign = adapter._job(board, "lseg.wd3.myworkdayjobs.com", "lseg", "Careers", {"title": "AR Analyst", "externalPath": "/job/Colombo/AR_R9", "locationsText": "Colombo, Sri Lanka"}, True)
    assert foreign.country_codes == []
    india = adapter._job(board, "lseg.wd3.myworkdayjobs.com", "lseg", "Careers", {"title": "AR Analyst", "externalPath": "/job/Bengaluru/AR_R8", "locationsText": ""}, True)
    assert india.country_codes == ["IN"] and india.location == "Bengaluru"


def test_tcs_ibegin_new_api_uses_xsrf_cookie_and_structured_experience():
    class TcsHttp(FakeHttp):
        def cookies(self, domain=""):
            assert domain == "ibegin.tcsapps.com"
            return {"XSRF-TOKEN": "tok-123"}

        def request(self, method, url, **kwargs):
            self.calls.append((method, url, None))

    seen_headers = {}

    def search(payload):
        assert payload["searchTerms"] == ["analyst"] and payload["resultsPerPage"] == 50
        return {"payload": {"last": True, "content": [
            {"id": "432449J", "title": "Business Analyst", "location": "Bengaluru", "domain": "BPS",
             "minimumExperienceInYears": 4, "maximumExperienceInYears": 7, "skills": ["Business Analysis"], "walkIn": False},
        ]}}

    http = TcsHttp(text={"https://ibegin.tcsapps.com/candidate/next/": "<html></html>"},
                   post={"https://ibegin.tcsapps.com/candidate/next/api/en-IN/search/jobs": search})
    original = http.post_json

    def post_json(url, payload, headers=None, timeout=None):
        seen_headers.update(headers or {})
        return original(url, payload, headers, timeout)

    http.post_json = post_json
    job = adapter_for("tcs_ibegin", http).list_jobs(Board("TCS", "tcs_ibegin", "analyst"))[0]
    assert seen_headers["next-xsrf-token"] == "tok-123"
    assert job.url == "https://ibegin.tcsapps.com/candidate/next/en-IN/jobs/432449J"
    assert "Experience: 4 - 7 years" in job.description
    assert legacy_url_key("https://ibegin.tcsapps.com/candidate/#/jobs/432449J") in job.all_legacy_keys()
