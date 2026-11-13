"""Gazetteer data for India geo resolution (all lowercase unless noted)."""

INDIA_COUNTRY_WORDS = ("india", "bharat", "pan india", "pan-india", "delhi ncr", "ncr")

INDIAN_STATES = (
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "chattisgarh", "goa", "gujarat",
    "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala", "madhya pradesh", "maharashtra",
    "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "rajasthan", "sikkim",
    "tamil nadu", "tamilnadu", "telangana", "tripura", "uttar pradesh", "uttarakhand", "uttaranchal",
    "west bengal", "andaman and nicobar", "dadra and nagar haveli", "daman and diu", "jammu and kashmir",
    "ladakh", "lakshadweep", "puducherry", "pondicherry", "nct of delhi", "national capital territory",
)

# Two-letter codes are only trusted next to an Indian city (they clash with US states).
INDIAN_STATE_CODES = frozenset({
    "ka", "mh", "tn", "tg", "ts", "ap", "dl", "hr", "up", "wb", "gj", "rj", "kl", "mp", "pb", "or", "od",
    "cg", "ct", "jh", "br", "as", "uk", "ut", "hp", "jk", "ga", "py", "ch",
})

# Unambiguous Indian cities, aliases, common misspellings and IT micro-locations.
INDIAN_CITIES = (
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
)

# Indian city names that also exist abroad; India only if the segment has no foreign marker.
AMBIGUOUS_INDIAN_CITIES = (
    "delhi", "hyderabad", "kochi", "salem", "kota", "surat", "punjab", "salt lake",
)

FOREIGN_COUNTRIES = (
    "united states", "united states of america", "usa", "u.s.a", "u.s.", "us", "america", "canada", "mexico",
    "brazil", "argentina", "chile", "colombia", "peru", "costa rica", "guatemala", "uruguay", "venezuela",
    "panama", "dominican republic", "puerto rico", "united kingdom", "uk", "u.k.", "great britain", "england",
    "scotland", "wales", "ireland", "northern ireland", "germany", "france", "spain", "portugal", "italy",
    "netherlands", "the netherlands", "belgium", "luxembourg", "switzerland", "austria", "poland",
    "czech republic", "czechia", "slovakia", "hungary", "romania", "bulgaria", "serbia", "croatia", "slovenia",
    "bosnia", "greece", "cyprus", "malta", "turkey", "turkiye", "ukraine", "lithuania", "latvia", "estonia",
    "finland", "sweden", "norway", "denmark", "iceland", "israel", "egypt", "morocco", "tunisia",
    "south africa", "nigeria", "kenya", "ghana", "uae", "u.a.e", "united arab emirates", "dubai", "abu dhabi",
    "saudi arabia", "ksa", "riyadh", "jeddah", "qatar", "doha", "kuwait", "bahrain", "oman", "jordan",
    "lebanon", "pakistan", "bangladesh", "sri lanka", "nepal", "bhutan", "maldives", "myanmar", "china",
    "hong kong", "macau", "taiwan", "japan", "south korea", "korea", "singapore", "malaysia", "indonesia",
    "philippines", "thailand", "vietnam", "viet nam", "cambodia", "australia", "new zealand", "kazakhstan",
    "georgia", "armenia", "azerbaijan", "russia",
    # major foreign cities that often appear without a country
    "london", "manchester", "edinburgh", "dublin", "paris", "berlin", "munich", "frankfurt", "hamburg",
    "amsterdam", "rotterdam", "brussels", "zurich", "geneva", "vienna", "warsaw", "krakow", "wroclaw", "prague",
    "budapest", "bucharest", "sofia", "madrid", "barcelona", "lisbon", "milan", "rome", "stockholm", "oslo",
    "copenhagen", "helsinki", "tel aviv", "cairo", "johannesburg", "cape town", "nairobi", "lagos", "toronto",
    "vancouver", "montreal", "ottawa", "calgary", "new york", "new york city", "nyc", "san francisco",
    "bay area", "los angeles", "seattle", "chicago", "boston", "austin", "dallas", "houston", "atlanta",
    "denver", "miami", "phoenix", "philadelphia", "washington dc", "washington, d.c.", "san jose", "san diego",
    "mountain view", "palo alto", "menlo park", "sunnyvale", "redmond", "bellevue", "foster city", "nashville",
    "charlotte", "raleigh", "pittsburgh", "minneapolis", "detroit", "salt lake city", "portland", "sydney",
    "melbourne", "brisbane", "perth", "auckland", "tokyo", "osaka", "seoul", "beijing", "shanghai", "shenzhen",
    "guangzhou", "taipei", "manila", "makati", "taguig", "cebu", "bangkok", "jakarta", "kuala lumpur",
    "kota kinabalu", "kota bharu", "penang", "ho chi minh", "hanoi", "karachi", "lahore", "islamabad",
    "dhaka", "colombo", "kathmandu", "sao paulo", "mexico city", "guadalajara", "bogota", "buenos aires",
    "santiago", "lima", "san jose costa rica", "emea", "latam", "americas", "north america", "europe",
)

US_STATES = (
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida",
    "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland",
    "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "north carolina", "north dakota", "ohio", "oklahoma",
    "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah",
    "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming", "district of columbia",
    "ontario", "quebec", "british columbia", "alberta", "manitoba", "saskatchewan", "nova scotia",
    "new brunswick", "indianapolis",
)

# Uppercase two-letter US state codes, matched case-sensitively after a comma or dash.
US_STATE_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY",
    "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND",
    "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    "ON", "QC", "BC", "AB", "MB", "SK", "NS",
})

UNKNOWN_LOCATION_RE = (
    r"^\s*(?:\d+\s+locations?|multiple locations?|various locations?|several locations?|remote|anywhere|"
    r"global|worldwide|work from home|wfh|hybrid|flexible|apac|asia|asia pacific|asia-pacific|"
    r"to be determined|tbd|n/?a|not specified|location)\s*$"
)

INDIA_COUNTRY_CODES = frozenset({"in", "ind", "india"})
