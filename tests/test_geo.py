import pytest

from jobfleet.geo import is_india_job, location_is_unknown, primary_india_city, resolve


@pytest.mark.parametrize(
    "location",
    [
        "Indianapolis, Indiana",  # defect: 'india' is a substring of 'indiana'
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
    assert resolve(location).status == "foreign"


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
        "New York; Bengaluru",  # multi-location postings count if any segment is India
    ],
)
def test_india_locations(location):
    assert resolve(location).status == "india"


def test_n_locations_and_remote_are_unknown():
    assert resolve("2 Locations").status == "unknown"
    assert resolve("Remote").status == "unknown"
    assert location_is_unknown("3 Locations")


def test_structured_country_code_wins():
    assert resolve("2 Locations", country_codes=["IN"]).basis == "structured"
    assert resolve("Remote", country_codes=["US"]).status == "foreign"
    assert resolve("", country_codes=["India"]).is_india  # Ashby/JSON-LD give country names


def test_text_india_beats_foreign_primary_country():
    # Lever's country field is only the primary location; allLocations may include India.
    assert resolve("Remote", country_codes=["US"], locations=["Bengaluru"]).is_india


def test_description_only_used_when_location_unknown():
    assert not is_india_job("Remote - United States", "We have offices in India and the US.")
    assert not is_india_job("Canada", "This company also has offices in India.")
    inferred = resolve("", description="This role is based in Bengaluru, India.")
    assert inferred.status == "india" and inferred.basis == "inferred"
    assert resolve("", description="Collaborate with our India team.").status == "unknown"


def test_primary_city_aliases():
    assert primary_india_city(["Bangalore, Karnataka"]) == "bengaluru"
    assert primary_india_city(["Gurgaon"]) == "gurugram"
    assert primary_india_city(["India"]) == "india"
