"""Synthetic records, always labeled and never returned as live provider results."""
from .database import db
from .models import CompanyCandidate
from .pipeline import upsert_candidate

COUNTRIES = [("US", "United States", "New York"), ("GB", "United Kingdom", "London"), ("DE", "Germany", "Berlin"), ("IN", "India", "Bengaluru"), ("SG", "Singapore", "Singapore"), ("AU", "Australia", "Sydney"), ("CA", "Canada", "Toronto"), ("FR", "France", "Paris")]
INDUSTRIES = ["SaaS", "E-commerce", "Fintech", "Logistics", "Retail", "Healthcare", "EdTech", "Travel", "Marketplace", "Analytics"]
PREFIXES = ["Northstar", "Cedar", "Aster", "Orbit", "Tandem", "Meridian", "Fable", "Signal"]
SUFFIXES = ["Labs", "Works", "Cloud", "Bridge", "Flow", "Collective", "Systems", "Studio"]


def seed_demo():
    if db().companies.count_documents({"demo": True}) > 0:
        return 0
    count = 0
    for i in range(80):
        code, country, city = COUNTRIES[i % len(COUNTRIES)]
        industry = INDUSTRIES[i % len(INDUSTRIES)]
        name = f"{PREFIXES[i % 8]} {SUFFIXES[(i // 8) % 8]} {i + 1}"
        amount = None if i % 7 == 0 else (i % 20 + 1) * 750_000
        candidate = CompanyCandidate(name=name, description=f"Fictional {industry.lower()} company created for ProspectIQ demo workflows.",
            location={"country_code": code, "country": country, "city": city}, industry=[industry],
            founded_year=2016 + i % 11, employees={"min": 10 + (i % 9) * 10, "max": 20 + (i % 9) * 10},
            funding={"total_amount_usd": amount, "original_currency": "USD" if amount is not None else None, "last_funding_date": None, "rounds": []},
            external_ids={"demo": str(i + 1)}, source_name="ProspectIQ demo generator", source_url="demo://synthetic", source_type="demo", demo=True)
        upsert_candidate(candidate)
        count += 1
    return count
