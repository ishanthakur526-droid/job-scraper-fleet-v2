"""Hand-curated place data that GeoNames does not cover (all lowercase).

GeoNames (``data/gazetteer.json.gz``, built by ``scripts/build_gazetteer.py``)
knows every country, state/province and city with 15,000+ people. This file
adds what job postings write that GeoNames lacks: country packs (spelling
variants, business districts and IT parks), multi-country regions ("EMEA")
and nicknames ("Bay Area").
"""

# ---------------------------------------------------------------- country packs
# strong: always that country. ambiguous: that country unless the segment says otherwise.
COUNTRY_PACKS: dict[str, dict[str, tuple[str, ...]]] = {
    "IN": {
        "country": ("india", "bharat", "pan india", "pan-india", "delhi ncr", "ncr"),
        "strong": (
            # states and union territories, incl. old spellings
            "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "chattisgarh", "goa", "gujarat",
            "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala", "madhya pradesh", "maharashtra",
            "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "rajasthan", "sikkim",
            "tamil nadu", "tamilnadu", "telangana", "tripura", "uttar pradesh", "uttarakhand", "uttaranchal",
            "west bengal", "andaman and nicobar", "dadra and nagar haveli", "daman and diu", "jammu and kashmir",
            "ladakh", "lakshadweep", "puducherry", "pondicherry", "nct of delhi", "national capital territory",
            # cities, aliases, common misspellings and IT micro-locations
            "bengaluru", "bangalore", "bengaluru urban", "bangalore urban", "bengaluru rural", "blr", "mumbai", "bombay",
            "navi mumbai", "thane", "new delhi", "gurugram", "gurgaon", "gurgoan", "gurugram haryana", "noida",
            "greater noida", "ghaziabad", "faridabad", "secunderabad", "cyberabad", "pune", "poona", "pimpri",
            "chinchwad", "pimpri-chinchwad", "hinjewadi", "hinjawadi", "kharadi", "magarpatta", "viman nagar",
            "chennai", "madras", "kolkata", "calcutta", "ahmedabad", "gandhinagar", "gift city", "vadodara", "baroda",
            "rajkot", "jaipur", "jodhpur", "udaipur", "lucknow", "kanpur", "indore", "bhopal", "nagpur", "nashik",
            "aurangabad", "chhatrapati sambhajinagar", "kolhapur", "solapur", "coimbatore", "madurai", "tiruchirappalli",
            "trichy", "tirupur", "tiruppur", "vellore", "hosur", "erode", "mysuru", "mysore", "mangaluru", "mangalore",
            "hubli", "hubballi", "dharwad", "belagavi", "belgaum", "manipal", "udupi", "davangere", "shimoga",
            "shivamogga", "tumkur", "cochin", "ernakulam", "kakkanad", "thiruvananthapuram", "trivandrum", "technopark",
            "infopark", "kozhikode", "calicut", "thrissur", "kollam", "kannur", "visakhapatnam", "vishakhapatnam",
            "vizag", "vijayawada", "guntur", "tirupati", "nellore", "kakinada", "rajahmundry", "warangal", "karimnagar",
            "bhubaneswar", "bhubaneshwar", "cuttack", "rourkela", "ranchi", "jamshedpur", "dhanbad", "bokaro", "patna",
            "guwahati", "shillong", "siliguri", "durgapur", "asansol", "kharagpur", "raipur", "bhilai", "dehradun",
            "haridwar", "roorkee", "shimla", "chandigarh", "mohali", "panchkula", "zirakpur", "ludhiana", "amritsar",
            "jalandhar", "patiala", "jammu", "srinagar", "agra", "aligarh", "meerut", "varanasi", "prayagraj", "allahabad",
            "gorakhpur", "bareilly", "moradabad", "jhansi", "gwalior", "jabalpur", "ujjain", "sonipat", "sonepat",
            "panipat", "karnal", "rohtak", "hisar", "ambala", "manesar", "bhiwadi", "neemrana", "ajmer", "bikaner",
            "alwar", "panaji", "panjim", "margao", "port blair", "gangtok", "imphal", "aizawl", "agartala", "itanagar",
            "kohima", "dimapur", "silvassa", "sriperumbudur", "chengalpattu", "tambaram", "perungudi", "sholinganallur",
            "siruseri", "guindy", "porur", "taramani", "ambattur", "whitefield", "electronic city", "electronics city",
            "marathahalli", "bellandur", "koramangala", "manyata", "yelahanka", "hebbal", "outer ring road",
            "hitec city", "hitech city", "hi-tech city", "gachibowli", "madhapur", "kondapur", "nanakramguda",
            "financial district hyderabad", "powai", "andheri", "goregaon", "malad", "vikhroli", "airoli", "ghansoli",
            "bandra kurla complex", "bkc", "lower parel", "worli", "nariman point", "kurla", "borivali", "kalyan",
            "dombivli", "vashi", "belapur", "cbd belapur", "panvel", "cyber city", "dlf cyber city", "sohna", "okhla",
            "nehru place", "connaught place", "new town kolkata", "rajarhat", "bilaspur",
        ),
        "ambiguous": ("delhi", "hyderabad", "kochi", "salem", "kota", "surat", "punjab", "salt lake"),
    },
}

# Canonical city for duplicate detection (two postings in "Bangalore" and "Bengaluru" are the same place).
CITY_CANONICAL = {
    "bangalore": "bengaluru", "bangalore urban": "bengaluru", "bengaluru urban": "bengaluru", "blr": "bengaluru",
    "bombay": "mumbai", "gurgaon": "gurugram", "gurgoan": "gurugram", "madras": "chennai", "calcutta": "kolkata",
    "poona": "pune", "trivandrum": "thiruvananthapuram", "cochin": "kochi", "vizag": "visakhapatnam",
    "vishakhapatnam": "visakhapatnam", "bhubaneshwar": "bhubaneswar", "baroda": "vadodara", "mysore": "mysuru",
    "mangalore": "mangaluru", "new delhi": "delhi", "secunderabad": "hyderabad", "sonepat": "sonipat",
    "new york city": "new york", "nyc": "new york", "frankfurt am main": "frankfurt", "koln": "cologne",
}

# Nicknames and areas that GeoNames has under another name.
EXTRA_PLACES: dict[str, str] = {
    "bay area": "US", "sf bay area": "US", "silicon valley": "US", "new york metro": "US", "dc metro": "US", "tri-state area": "US",
    "cebu": "PH", "metro manila": "PH", "ncr philippines": "PH", "khyber": "PK", "greater london": "GB", "greater toronto area": "CA",
    "gta": "CA", "randstad": "NL", "greater manchester": "GB",
}

# Multi-country regions: a job in "EMEA" is foreign for an India profile, unknown for a Germany profile.
MACRO_REGIONS: dict[str, tuple[str, ...]] = {
    "europe": ("@EU",), "eu": ("@EU",), "european union": ("@EU",), "emea": ("@EU", "@AF", "@ME"), "eemea": ("@EU", "@AF", "@ME"),
    "mena": ("@AF", "@ME"), "middle east": ("@ME",), "gcc": ("@ME",), "africa": ("@AF",),
    "latam": ("@SA", "MX", "GT", "CR", "PA", "SV", "HN", "NI", "DO", "PR"), "latin america": ("@SA", "MX", "GT", "CR", "PA", "SV", "HN", "NI", "DO", "PR"),
    "south america": ("@SA",), "central america": ("MX", "GT", "CR", "PA", "SV", "HN", "NI", "BZ"),
    "americas": ("@NA", "@SA"), "north america": ("US", "CA", "MX"), "nordics": ("SE", "NO", "DK", "FI", "IS"),
    "scandinavia": ("SE", "NO", "DK"), "dach": ("DE", "AT", "CH"), "benelux": ("BE", "NL", "LU"), "anz": ("AU", "NZ"),
    "apac": ("@AS", "@OC"), "asia": ("@AS",), "asia pacific": ("@AS", "@OC"), "oceania": ("@OC",), "southeast asia": ("SG", "MY", "ID", "TH", "VN", "PH", "KH", "LA", "MM", "BN"),
}
MIDDLE_EAST = ("AE", "SA", "QA", "KW", "BH", "OM", "JO", "LB", "IL", "IQ", "IR", "SY", "YE", "TR", "EG", "PS")

# Upper-case three-letter country codes trusted inside location strings ("IND-BLR-...", "USA-CA-San Jose").
ISO3_ALLOWED = frozenset({
    "IND", "USA", "GBR", "CAN", "AUS", "NZL", "DEU", "FRA", "ESP", "ITA", "NLD", "BEL", "CHE", "AUT", "POL", "IRL", "SWE", "DNK",
    "FIN", "PRT", "CZE", "HUN", "ROU", "BGR", "GRC", "TUR", "ISR", "EGY", "ZAF", "NGA", "KEN", "SAU", "QAT", "PAK", "BGD",
    "LKA", "NPL", "CHN", "HKG", "TWN", "JPN", "KOR", "SGP", "MYS", "IDN", "PHL", "THA", "VNM", "MEX", "BRA", "ARG", "CHL",
    "CRI", "URY", "UKR", "SVK", "HRV", "SRB", "LTU", "LVA", "EST", "LUX", "ARE",
})

# Words that are also the names of small towns somewhere; never treated as places.
STOP_KEYS = frozenset({
    "central", "hub", "bay", "metro", "university", "airport", "mission", "office", "home", "global", "field", "virtual",
    "national", "flexible", "various", "multiple", "other", "location", "locations", "onsite", "site", "campus", "park",
    "tower", "plaza", "main", "center", "centre", "north", "south", "east", "west", "city", "new", "old", "saint", "st",
    "floor", "building", "road", "street", "sector", "phase", "block", "area", "zone", "hills", "station", "hospital",
    "college", "district", "region", "regional", "greater", "industrial", "business", "technology", "tech",
    "headquarters", "hq", "worldwide", "anywhere", "work", "from", "and", "the", "or", "of", "de", "la", "remote",
    "hybrid", "data", "time", "sales", "marine", "union", "victory", "progress", "independence", "liberty", "commerce",
    "industry", "enterprise", "temple", "garden", "gardens", "lake", "valley", "springs", "heights", "village", "town",
    "corporate", "branch", "store", "plant", "warehouse", "distribution", "lab", "labs", "studio", "team", "teams",
    "san", "santa", "los", "las", "el", "port", "fort", "mount", "western", "eastern", "northern", "southern",
})

UNKNOWN_LOCATION_RE = (
    r"^\s*(?:\d+\s+locations?|multiple locations?|various locations?|several locations?|remote|anywhere|"
    r"global|worldwide|work from home|wfh|hybrid|flexible|"
    r"to be determined|tbd|n/?a|not specified|location)\s*$"
)
REMOTE_RE = r"\b(?:remote|work from home|wfh|work from anywhere|telecommut\w*|home[- ]based|virtual)\b"
