import pytest

from jobfleet.geo import CityFilter, country_code, locate, location_is_unknown, primary_city, resolve

INDIA = ("IN",)


@pytest.mark.parametrize(
    "location",
    [
        "Indianapolis, Indiana",  # v2 defect: 'india' is a substring of 'indiana'
        "Carmel, Indiana",
        "Remote - Indiana",
        "Indianapolis, IN",
        "Indianapolis, Indiana, United States",
        "Indian Wells, California",
        "Jakarta, Indonesia",
        "Remote - United States",
        "US-Remote",
        "Remote, NV, us",
        "London, United Kingdom",
        "Delhi, NY",
        "Hyderabad, Pakistan",
        "Kochi, Japan",
        "Salem, OR",
        "Kota Kinabalu",
        "Lahore, Punjab, Pakistan",
        "Salt Lake City, UT",
        "APAC; Singapore, Central, Singapore",
        "Toronto, ON",
    ],
)
def test_foreign_locations_are_not_india(location):
    assert resolve(location, target_codes=INDIA).status == "foreign"


@pytest.mark.parametrize(
    "location",
    [
        "Lucknow",
        "Gurgoan, in",
        "Vadodara, GJ, in",
        "IND-BLR-Divyasree Technopolis",
        "IND Visakhapatnam - SRK Destiny, 6th & 7th Flr",
        "Chennai (ex Madras)",
        "Chennai, TN, IN",
        "Bengaluru Urban, KA, India",
        "R271- Noida",
        "India - Mumbai",
        "Remote - India",
        "Hyderabad",
        "Delhi",
        "Mohali, Punjab",
        "Salt Lake, Kolkata",
        "Coimbatore",
        "Trivandrum",
        "Kochi, Kerala",
        "Aligarh, Uttar Pradesh",
        "New York; Bengaluru",  # multi-location postings count if any segment is in a target country
        "Deoria, UP_East",  # GeoNames knows towns the v3 list did not
    ],
)
def test_india_locations(location):
    assert resolve(location, target_codes=INDIA).status == "target"


@pytest.mark.parametrize(
    "location, country",
    [
        ("San Jose, CA", "US"), ("Toronto, CA", "CA"), ("Austin, TX", "US"), ("Paris, TX", "US"), ("Paris", "FR"),
        ("Melbourne, FL", "US"), ("Melbourne, VIC", "AU"), ("London, UK", "GB"), ("London, ON", "CA"), ("Cambridge, MA", "US"),
        ("US-NY-New York", "US"), ("USA-CA-San Jose", "US"), ("Washington, D.C.", "US"), ("Atlanta, Georgia", "US"),
        ("Tbilisi, Georgia", "GE"), ("München", "DE"), ("Zürich", "CH"), ("Dubai, UAE", "AE"), ("Hyderabad, Sindh", "PK"),
        ("Florida", "US"), ("Manchester", "GB"), ("Vancouver, WA", "US"), ("Bay Area", "US"), ("Kraków", "PL"),
    ],
)
def test_worldwide_locations(location, country):
    assert locate(location).contenders == (country,)


def test_ambiguous_city_is_unknown_not_guessed():
    assert len(locate("Cambridge").contenders) > 1
    assert resolve("Cambridge", target_codes=("GB",)).status == "unknown"
    assert resolve("Cambridge", target_codes=INDIA).status == "foreign"  # both candidates are foreign for India


def test_macro_regions_depend_on_the_target():
    assert resolve("EMEA", target_codes=INDIA).status == "foreign"
    assert resolve("EMEA", target_codes=("DE",)).status == "unknown"
    assert resolve("APAC", target_codes=INDIA).status == "unknown"


def test_n_locations_and_remote_are_unknown():
    assert resolve("2 Locations", target_codes=INDIA).status == "unknown"
    assert resolve("Remote", target_codes=INDIA).status == "unknown"
    assert location_is_unknown("3 Locations")


def test_structured_country_code_wins():
    assert resolve("2 Locations", country_codes=["IN"], target_codes=INDIA).basis == "structured"
    assert resolve("Remote", country_codes=["US"], target_codes=INDIA).status == "foreign"
    assert resolve("", country_codes=["India"], target_codes=INDIA).is_target  # Ashby/JSON-LD give country names
    assert resolve("", country_codes=["USA"], target_codes=("US",)).is_target


def test_text_target_beats_foreign_primary_country():
    # Lever's country field is only the primary location; allLocations may include India.
    assert resolve("Remote", country_codes=["US"], locations=["Bengaluru"], target_codes=INDIA).is_target


def test_description_only_used_when_location_unknown():
    assert not resolve("Remote - United States", description="We have offices in India and the US.", target_codes=INDIA).is_target
    assert not resolve("Canada", description="This company also has offices in India.", target_codes=INDIA).is_target
    inferred = resolve("", description="This role is based in Bengaluru, India.", target_codes=INDIA)
    assert inferred.status == "target" and inferred.basis == "inferred"
    assert resolve("", description="Collaborate with our India team.", target_codes=INDIA).status == "unknown"
    assert resolve("Remote", description="This is a remote role within the United States.", target_codes=("US",)).is_target
    assert resolve("Remote", description="Candidates must reside in the United States.", target_codes=("GB",)).status == "foreign"


def test_country_codes_from_names():
    assert [country_code(x) for x in ("India", "IN", "ind", "USA", "United States", "uk", "United Kingdom", "Deutschland", "Inda")] == [
        "IN", "IN", "IN", "US", "US", "GB", "GB", "DE", ""
    ]


def test_primary_city_aliases():
    assert primary_city(["Bangalore, Karnataka"]) == "bengaluru"
    assert primary_city(["Gurgaon"]) == "gurugram"
    assert primary_city(["New York, NY"]) == primary_city(["NYC"]) == "new york"
    assert primary_city(["India"]) == "any"


def test_city_filter_understands_aliases():
    wanted = CityFilter(["Bangalore", "Pune"])
    assert wanted.matches(["Bengaluru, Karnataka, India"]) and wanted.matches(["Hinjewadi; Pune"])
    assert not wanted.matches(["Mumbai"])
    assert not CityFilter([])
