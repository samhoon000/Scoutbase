from functools import lru_cache
from pymongo import MongoClient, ASCENDING, DESCENDING
from .config import settings


@lru_cache
def client() -> MongoClient:
    if not settings.mongodb_uri:
        if settings.demo_mode:
            import mongomock
            return mongomock.MongoClient()
        raise RuntimeError("MONGODB_URI is required when DEMO_MODE=false")
    return MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=4000)


def db():
    return client()[settings.database_name]


def initialize() -> None:
    database = db()
    database.command("ping")
    companies = database.companies
    companies.create_index([("domain", ASCENDING)], unique=True, partialFilterExpression={"domain": {"$type": "string"}})
    companies.create_index([("external_keys", ASCENDING)], unique=True, partialFilterExpression={"external_keys": {"$type": "string"}})
    companies.create_index([("name_normalized", ASCENDING), ("location.country_code", ASCENDING)])
    companies.create_index([("location.country_code", ASCENDING), ("industry", ASCENDING), ("prospect_score", DESCENDING)])
    companies.create_index([("funding.total_amount_usd", DESCENDING)])
    companies.create_index([("funding.last_funding_date", DESCENDING)])
    companies.create_index([("employees.min", ASCENDING)])
    companies.create_index([("founded_year", DESCENDING)])
    companies.create_index([("signals.growth_score", DESCENDING)])
    companies.create_index([("prospect_score", DESCENDING)])
    companies.create_index([("demo", ASCENDING)])
    database.saved_companies.create_index([("user_id", ASCENDING), ("company_id", ASCENDING)], unique=True)
    database.outreach.create_index([("user_id", ASCENDING), ("company_id", ASCENDING)])
    database.searches.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    database.jobs.create_index([("created_at", DESCENDING)])
    database.provider_cache.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    database.provider_cache.create_index([("provider", ASCENDING), ("key", ASCENDING)], unique=True)
    database.api_usage.create_index([("provider", ASCENDING), ("date", ASCENDING)], unique=True)
