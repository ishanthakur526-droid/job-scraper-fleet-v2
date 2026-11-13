"""Ready-made role families. The setup wizard, the GitHub form and the example
profiles copy from here, so a user only picks names ("Software Engineering",
"Marketing") instead of typing title lists.

Each family lists:
- ``titles``          job titles that belong to it (word order does not matter)
- ``title_keywords``  a title containing one of these is a weaker match
- ``keywords``        description words that raise the score
- ``domains``         job domains it owns (otherwise excluded, see ``levels.DOMAINS``)
- ``search``          what to type into job-board search boxes
- ``abbreviations``   title shorthands to expand before matching
"""

from __future__ import annotations

from typing import Any

FAMILIES: dict[str, dict[str, Any]] = {
    "software_engineering": {
        "name": "Software Engineering",
        "domains": ["engineering"],
        "titles": [
            "Software Engineer", "Software Developer", "Software Development Engineer", "Backend Engineer", "Backend Developer",
            "Frontend Engineer", "Frontend Developer", "Full Stack Engineer", "Full Stack Developer", "Web Developer",
            "Application Developer", "Java Developer", "Python Developer", ".NET Developer", "Mobile Developer", "iOS Developer",
            "Android Developer", "Member of Technical Staff",
        ],
        "title_keywords": ["software", "backend", "frontend", "full stack", "web developer"],
        "keywords": ["python", "java", "javascript", "typescript", "react", "node", "golang", "c#", ".net", "sql", "aws", "azure",
                     "kubernetes", "docker", "microservices", "rest api", "git", "ci/cd"],
        "search": ["software engineer", "software developer", "backend engineer", "full stack developer"],
        "abbreviations": {"sde": "software development engineer", "swe": "software engineer", "fullstack": "full stack"},
    },
    "devops_cloud": {
        "name": "DevOps & Cloud",
        "domains": ["engineering", "it_operations"],
        "titles": [
            "DevOps Engineer", "Site Reliability Engineer", "Cloud Engineer", "Platform Engineer", "Infrastructure Engineer",
            "Cloud Operations Engineer", "Build and Release Engineer", "Systems Engineer", "Cloud Architect",
        ],
        "title_keywords": ["devops", "cloud", "site reliability", "platform", "infrastructure", "kubernetes"],
        "keywords": ["aws", "azure", "gcp", "terraform", "kubernetes", "docker", "linux", "ci/cd", "jenkins", "ansible", "prometheus",
                     "monitoring", "python", "bash"],
        "search": ["devops engineer", "site reliability engineer", "cloud engineer"],
        "abbreviations": {"sre": "site reliability engineer"},
    },
    "data_engineering": {
        "name": "Data Engineering",
        "domains": ["engineering"],
        "titles": ["Data Engineer", "Big Data Engineer", "ETL Developer", "Analytics Engineer", "Data Platform Engineer",
                   "Data Warehouse Engineer", "Data Integration Engineer"],
        "title_keywords": ["data engineer", "etl", "data pipeline", "data platform", "data warehouse"],
        "keywords": ["sql", "python", "spark", "airflow", "dbt", "snowflake", "databricks", "kafka", "etl", "aws", "bigquery", "redshift"],
        "search": ["data engineer", "analytics engineer", "etl developer"],
    },
    "data_science": {
        "name": "Data Science & ML",
        "domains": ["data_science_ml", "engineering"],
        "titles": ["Data Scientist", "Machine Learning Engineer", "ML Engineer", "AI Engineer", "Applied Scientist", "Research Scientist",
                   "NLP Engineer", "Computer Vision Engineer", "Decision Scientist"],
        "title_keywords": ["data scientist", "machine learning", "deep learning", "artificial intelligence"],
        "keywords": ["python", "machine learning", "statistics", "pytorch", "tensorflow", "scikit-learn", "sql", "nlp", "llm",
                     "deep learning", "modeling", "experimentation"],
        "search": ["data scientist", "machine learning engineer", "ai engineer"],
        "abbreviations": {"ai": "artificial intelligence"},
    },
    "data_analytics": {
        "name": "Data & BI Analytics",
        "domains": [],
        "titles": [
            "Data Analyst", "Business Intelligence Analyst", "BI Analyst", "BI Developer", "Reporting Analyst", "Insights Analyst",
            "Business Analyst", "Marketing Analyst", "Product Analyst", "Operations Analyst", "Analytics Associate",
            "Power BI Developer", "Tableau Developer", "Dashboard Developer",
        ],
        "title_keywords": ["analytics", "business intelligence", "dashboard", "insights", "reporting", "data analysis", "power bi", "tableau"],
        "keywords": ["sql", "excel", "power bi", "tableau", "looker", "dashboard", "reporting", "analytics", "insights", "data analysis",
                     "data visualization", "kpi", "python"],
        "search": ["data analyst", "business analyst", "bi analyst"],
        "abbreviations": {"bie": "business intelligence engineer", "bi": "business intelligence"},
    },
    "research": {
        "name": "Research & Insights",
        "domains": [],
        "titles": ["Research Analyst", "Market Research Analyst", "Competitive Intelligence Analyst", "Consumer Insights Analyst",
                   "Secondary Research Analyst", "Equity Research Analyst", "Market Intelligence Analyst", "Research Associate"],
        "title_keywords": ["research", "market intelligence", "competitive intelligence"],
        "keywords": ["research", "market research", "secondary research", "primary research", "competitive intelligence",
                     "consumer insights", "industry analysis", "market sizing", "survey"],
        "search": ["research analyst", "market research analyst"],
        "abbreviations": {"mi": "market intelligence"},
    },
    "excel_mis": {
        "name": "Excel / MIS Reporting",
        "domains": [],
        "titles": ["MIS Executive", "MIS Analyst", "Excel Specialist", "Excel Analyst", "Reporting Executive", "Google Sheets Specialist",
                   "Spreadsheet Developer", "Data Operations Analyst", "Reconciliation Analyst"],
        "title_keywords": ["mis", "excel", "reconciliation", "spreadsheet"],
        "keywords": ["excel", "advanced excel", "mis", "vlookup", "pivot", "macros", "vba", "google sheets", "reporting", "dashboard"],
        "search": ["mis executive", "mis analyst", "excel analyst"],
    },
    "product_management": {
        "name": "Product Management",
        "domains": [],
        "titles": ["Product Manager", "Associate Product Manager", "Product Owner", "Technical Product Manager", "Product Specialist",
                   "Product Operations Manager"],
        "title_keywords": ["product manager", "product owner", "product management"],
        "keywords": ["roadmap", "stakeholders", "user research", "agile", "scrum", "product strategy", "a/b testing", "jira",
                     "requirements", "analytics", "go-to-market"],
        "search": ["product manager", "product owner"],
        "abbreviations": {"apm": "associate product manager", "tpm": "technical product manager", "pm": "product manager"},
    },
    "project_management": {
        "name": "Project & Program Management",
        "domains": [],
        "titles": ["Project Manager", "Program Manager", "Project Coordinator", "Scrum Master", "PMO Analyst", "Delivery Manager",
                   "Project Associate", "Project Analyst"],
        "title_keywords": ["project", "program", "pmo", "scrum"],
        "keywords": ["pmp", "prince2", "agile", "scrum", "stakeholder", "budget", "timeline", "risk", "jira", "ms project", "planning"],
        "search": ["project manager", "project coordinator", "program manager"],
    },
    "design": {
        "name": "Design (UX/UI)",
        "domains": ["design"],
        "titles": ["UX Designer", "UI Designer", "Product Designer", "UX/UI Designer", "Visual Designer", "Interaction Designer",
                   "Graphic Designer", "UX Researcher", "Web Designer"],
        "title_keywords": ["designer", "ux", "ui", "user experience"],
        "keywords": ["figma", "sketch", "adobe", "prototyping", "wireframes", "user research", "design systems", "usability",
                     "illustrator", "photoshop"],
        "search": ["ux designer", "product designer", "ui designer"],
    },
    "qa_testing": {
        "name": "QA & Testing",
        "domains": ["qa_testing", "engineering"],
        "titles": ["QA Engineer", "Test Engineer", "QA Analyst", "Software Tester", "Automation Tester", "Test Automation Engineer",
                   "Quality Assurance Engineer", "Test Analyst", "SDET"],
        "title_keywords": ["qa", "test", "testing", "quality assurance", "automation"],
        "keywords": ["selenium", "cypress", "playwright", "test automation", "manual testing", "api testing", "jira", "java", "python",
                     "test cases", "regression"],
        "search": ["qa engineer", "software tester", "test automation engineer"],
        "abbreviations": {"sdet": "software development engineer in test"},
    },
    "cybersecurity": {
        "name": "Cybersecurity",
        "domains": ["security", "it_operations"],
        "titles": ["Security Analyst", "Cyber Security Analyst", "SOC Analyst", "Information Security Analyst", "Security Engineer",
                   "Penetration Tester", "GRC Analyst", "Security Consultant"],
        "title_keywords": ["security", "cyber", "soc", "infosec"],
        "keywords": ["siem", "splunk", "incident response", "vulnerability", "iso 27001", "nist", "firewall", "threat", "soc",
                     "penetration testing"],
        "search": ["security analyst", "soc analyst", "cyber security"],
    },
    "it_support": {
        "name": "IT Support & Systems",
        "domains": ["it_operations", "it_systems", "non_office"],
        "titles": ["IT Support Specialist", "IT Support Engineer", "Help Desk Technician", "Service Desk Analyst", "Desktop Support Engineer",
                   "IT Technician", "System Administrator", "Network Administrator", "Technical Support Engineer", "Systems Analyst"],
        "title_keywords": ["it support", "help desk", "service desk", "desktop support", "system administrator", "network"],
        "keywords": ["windows", "active directory", "office 365", "itil", "ticketing", "servicenow", "networking", "troubleshooting",
                     "linux", "hardware"],
        "search": ["it support", "help desk", "system administrator"],
    },
    "marketing": {
        "name": "Marketing",
        "domains": ["martech"],
        "titles": [
            "Marketing Executive", "Marketing Coordinator", "Marketing Specialist", "Marketing Associate", "Marketing Assistant",
            "Digital Marketing Executive", "Digital Marketing Specialist", "Social Media Executive", "Social Media Coordinator",
            "SEO Specialist", "Content Marketing Executive", "Performance Marketing Executive", "Brand Executive",
            "Growth Marketing Associate", "Email Marketing Specialist", "Campaign Executive", "Marketing Officer",
        ],
        "title_keywords": ["marketing", "seo", "social media", "brand", "campaign", "growth"],
        "keywords": ["google ads", "meta ads", "seo", "sem", "content", "social media", "hubspot", "google analytics", "email marketing",
                     "crm", "campaigns", "copywriting"],
        "search": ["marketing executive", "digital marketing", "marketing coordinator"],
        "abbreviations": {"smm": "social media marketing"},
    },
    "sales": {
        "name": "Sales & Business Development",
        "domains": ["sales"],
        "titles": ["Sales Executive", "Sales Representative", "Business Development Executive", "Business Development Representative",
                   "Sales Development Representative", "Account Executive", "Inside Sales Representative", "Sales Associate",
                   "Account Manager", "Business Development Associate"],
        "title_keywords": ["sales", "business development", "account executive"],
        "keywords": ["crm", "salesforce", "b2b", "pipeline", "quota", "lead generation", "negotiation", "prospecting", "cold calling",
                     "saas"],
        "search": ["sales executive", "business development", "account executive"],
        "abbreviations": {"bdr": "business development representative", "sdr": "sales development representative",
                          "bde": "business development executive"},
    },
    "customer_success": {
        "name": "Customer Success & Support",
        "domains": ["customer_support"],
        "titles": ["Customer Success Manager", "Customer Success Associate", "Customer Success Specialist", "Customer Support Specialist",
                   "Customer Service Representative", "Customer Support Representative", "Client Success Associate",
                   "Technical Support Specialist", "Customer Experience Associate", "Support Specialist"],
        "title_keywords": ["customer success", "customer support", "customer service", "client success", "customer experience"],
        "keywords": ["crm", "zendesk", "salesforce", "onboarding", "retention", "churn", "nps", "saas", "customer satisfaction",
                     "intercom"],
        "search": ["customer success", "customer support", "customer service"],
        "abbreviations": {"csm": "customer success manager"},
    },
    "hr_recruiting": {
        "name": "HR & Recruiting",
        "domains": ["hr", "recruiting"],
        "titles": ["HR Executive", "HR Generalist", "HR Coordinator", "HR Associate", "HR Assistant", "Recruiter", "Technical Recruiter",
                   "Talent Acquisition Specialist", "Talent Acquisition Executive", "HR Business Partner", "People Operations Specialist",
                   "Payroll Specialist"],
        "title_keywords": ["hr", "human resources", "recruiter", "talent acquisition", "people operations", "recruitment"],
        "keywords": ["recruitment", "onboarding", "hris", "workday", "payroll", "employee relations", "sourcing", "ats", "compliance"],
        "search": ["hr executive", "recruiter", "talent acquisition"],
        "abbreviations": {"hrbp": "hr business partner"},
    },
    "finance_accounting": {
        "name": "Finance & Accounting",
        "domains": [],
        "titles": ["Financial Analyst", "Finance Analyst", "FP&A Analyst", "Accountant", "Staff Accountant", "Accounts Payable",
                   "Accounts Receivable", "Finance Associate", "Audit Associate", "Tax Associate", "Credit Analyst", "Treasury Analyst",
                   "Accounts Executive", "Bookkeeper"],
        "title_keywords": ["finance", "financial", "accounting", "accountant", "fpa", "audit", "tax", "treasury"],
        "keywords": ["excel", "gaap", "ifrs", "reconciliation", "sap", "oracle", "financial modeling", "budgeting", "forecasting",
                     "variance analysis", "accounts payable", "month-end close"],
        "search": ["financial analyst", "accountant", "finance analyst"],
        "abbreviations": {"ar": "accounts receivable", "ap": "accounts payable", "p2p": "procure to pay", "o2c": "order to cash",
                          "r2r": "record to report"},
    },
    "operations_supply_chain": {
        "name": "Operations & Supply Chain",
        "domains": [],
        "titles": ["Operations Analyst", "Operations Associate", "Operations Executive", "Operations Coordinator", "Supply Chain Analyst",
                   "Logistics Coordinator", "Procurement Analyst", "Procurement Executive", "Purchasing Analyst", "Inventory Analyst",
                   "Demand Planner", "Business Operations Associate"],
        "title_keywords": ["operations", "supply chain", "logistics", "procurement", "inventory", "purchasing", "planning"],
        "keywords": ["excel", "sap", "erp", "inventory", "logistics", "procurement", "vendor", "forecasting", "sql", "process improvement"],
        "search": ["operations analyst", "supply chain analyst", "procurement"],
    },
    "content_writing": {
        "name": "Content & Writing",
        "domains": ["content"],
        "titles": ["Content Writer", "Copywriter", "Technical Writer", "Content Strategist", "Content Specialist", "Content Executive",
                   "Editor", "Communications Specialist", "Communications Executive"],
        "title_keywords": ["content", "writer", "copywriter", "editor", "communications"],
        "keywords": ["writing", "editing", "seo", "content strategy", "cms", "wordpress", "storytelling", "proofreading", "research"],
        "search": ["content writer", "copywriter", "technical writer"],
    },
    "legal_compliance": {
        "name": "Legal & Compliance",
        "domains": ["legal"],
        "titles": ["Legal Associate", "Legal Counsel", "Paralegal", "Legal Analyst", "Compliance Analyst", "Compliance Officer",
                   "Contract Analyst", "KYC Analyst", "AML Analyst", "Risk Analyst"],
        "title_keywords": ["legal", "compliance", "kyc", "aml", "contract", "regulatory"],
        "keywords": ["compliance", "regulatory", "contracts", "kyc", "aml", "risk", "policy", "legal research", "due diligence"],
        "search": ["compliance analyst", "legal associate", "kyc analyst"],
    },
}


def family_ids() -> list[str]:
    return list(FAMILIES)


def family(family_id: str) -> dict[str, Any]:
    return FAMILIES[family_id]


def find(text: str) -> str:
    """Family id for a typed name ('software', 'Marketing', 'data science'); '' if none matches."""
    wanted = text.strip().lower()
    for fid, info in FAMILIES.items():
        if wanted in (fid, fid.replace("_", " "), info["name"].lower()):
            return fid
    for fid, info in FAMILIES.items():
        if wanted and (wanted in info["name"].lower() or wanted in fid.replace("_", " ")):
            return fid
    return ""
