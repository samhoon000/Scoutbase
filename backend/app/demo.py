"""Synthetic records, always labeled and never returned as live provider results."""
from .database import db
from datetime import timedelta
from .models import CompanyCandidate, now
from .pipeline import upsert_candidate

COUNTRIES = [("US", "United States", "New York"), ("GB", "United Kingdom", "London"), ("DE", "Germany", "Berlin"), ("IN", "India", "Bengaluru"), ("SG", "Singapore", "Singapore"), ("AU", "Australia", "Sydney"), ("CA", "Canada", "Toronto"), ("NL", "Netherlands", "Amsterdam"), ("FR", "France", "Paris"), ("JP", "Japan", "Tokyo")]
INDUSTRIES = ["SaaS", "E-commerce", "Fintech", "Logistics", "Retail", "Healthcare", "EdTech", "Travel", "Marketplace", "Analytics", "D2C"]
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
        funding_date = now() - timedelta(days=30 * (3 + i % 38)) if amount is not None else None
        stage = ["Pre-seed", "Seed", "Series A", "Series B"][i % 4] if amount is not None else None
        round_data = {"round_type": stage, "amount": amount, "amount_usd": amount, "currency": "USD", "date": funding_date, "investors": []} if amount is not None else None
        candidate = CompanyCandidate(name=name, description=f"Fictional {industry.lower()} company created for ProspectIQ demo workflows.",
            location={"country_code": code, "country": country, "city": city}, industry=[industry],
            founded_year=2016 + i % 11, employees={"min": 10 + (i % 9) * 10, "max": 20 + (i % 9) * 10},
            funding={"total_amount_usd": amount, "original_currency": "USD" if amount is not None else None,
                     "funding_stage": stage, "last_funding_date": funding_date, "last_round": round_data,
                     "rounds": [round_data] if round_data else []},
            external_ids={"demo": str(i + 1)}, source_name="ProspectIQ demo generator", source_url="demo://synthetic", source_type="demo", demo=True)
        upsert_candidate(candidate)
        count += 1
    return count
