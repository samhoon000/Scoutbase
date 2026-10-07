from pymongo import ASCENDING, DESCENDING

# Explicit names make schema initialization safe to repeat.
INDEXES = {
    "companies": [
        ("domain_unique", [("domain", ASCENDING)], {"unique": True, "partialFilterExpression": {"domain": {"$type": "string"}}}),
        ("external_key_unique", [("external_keys", ASCENDING)], {"unique": True, "partialFilterExpression": {"external_keys": {"$type": "string"}}}),
        ("name_country", [("name_normalized", ASCENDING), ("location.country_code", ASCENDING)], {}),
        ("name_country_city", [("name_normalized", ASCENDING), ("location.country_code", ASCENDING), ("location.city", ASCENDING)], {}),
        ("website", [("website", ASCENDING)], {}),
        ("linkedin_url", [("linkedin_url", ASCENDING)], {}),
        ("country_industry_score", [("location.country_code", ASCENDING), ("industry", ASCENDING), ("prospect_score", DESCENDING)], {}),
        ("city", [("location.city", ASCENDING)], {}),
        ("founded_year", [("founded_year", DESCENDING)], {}),
        ("employees_min", [("employees.min", ASCENDING)], {}),
        ("employees_max", [("employees.max", ASCENDING)], {}),
        ("funding_total", [("funding.total_amount_usd", DESCENDING)], {}),
        ("funding_recent", [("funding.last_funding_date", DESCENDING)], {}),
        ("prospect_score", [("prospect_score", DESCENDING)], {}),
        ("growth_score", [("signals.growth_score", DESCENDING)], {}),
    ],
    "funding_rounds": [
        ("company_date", [("company_id", ASCENDING), ("date", DESCENDING)], {}),
    ],
    "people": [
        ("company_id", [("company_id", ASCENDING)], {}),
        ("linkedin_url", [("linkedin_url", ASCENDING)], {}),
    ],
    "sources": [
        ("company_source", [("company_id", ASCENDING), ("source_url", ASCENDING)], {}),
        ("source_url", [("source_url", ASCENDING)], {}),
    ],
    "saved_companies": [
        ("user_company_unique", [("user_id", ASCENDING), ("company_id", ASCENDING)], {"unique": True}),
    ],
    "outreach": [
        ("user_company", [("user_id", ASCENDING), ("company_id", ASCENDING)], {}),
        ("user_status", [("user_id", ASCENDING), ("status", ASCENDING)], {}),
    ],
    "searches": [
        ("user_created", [("user_id", ASCENDING), ("created_at", DESCENDING)], {}),
    ],
    "discovery_jobs": [
        ("status_created", [("status", ASCENDING), ("created_at", DESCENDING)], {}),
    ],
    "provider_cache": [
        ("provider_key_unique", [("provider", ASCENDING), ("key", ASCENDING)], {"unique": True}),
        ("expires_ttl", [("expires_at", ASCENDING)], {"expireAfterSeconds": 0}),
    ],
    "api_usage": [
        ("provider_date_unique", [("provider", ASCENDING), ("date", ASCENDING)], {"unique": True}),
    ],
}

REQUIRED_COLLECTIONS = tuple(INDEXES)
