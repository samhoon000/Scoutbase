import logging
from datetime import timedelta
from pymongo import ReturnDocument
from .database import db
from .models import CompanyCandidate, SearchCriteria, now
from .normalize import domain_from_url, normalized_name, safe_public_url, source_record
from .providers import live_providers
from .scoring import score_company

log = logging.getLogger(__name__)


def persist_related(company_id, candidate: CompanyCandidate, source: dict):
    database = db()
    database.sources.update_one({"company_id": company_id, "source_url": source["source_url"]},
        {"$set": {"company_id": company_id, **source}}, upsert=True)
    for person in candidate.founders + candidate.executives:
        if not person.get("name"):
            continue
        identity = {"company_id": company_id, "name": person["name"], "role": person.get("role"), "source_url": source["source_url"]}
        database.people.update_one(identity, {"$set": {**identity, "verified_at": source["collected_at"]}}, upsert=True)
    for round_data in candidate.funding.get("rounds", []):
        identity = {"company_id": company_id, "date": round_data.get("date"), "round_type": round_data.get("round_type"), "source_url": source["source_url"]}
        database.funding_rounds.update_one(identity, {"$set": {**round_data, **identity}}, upsert=True)


def upsert_candidate(candidate: CompanyCandidate):
    database = db()
    candidate.website = safe_public_url(candidate.website)
    candidate.linkedin_url = safe_public_url(candidate.linkedin_url)
    domain = domain_from_url(candidate.website)
    keys = [f"{provider}:{value}" for provider, value in candidate.external_ids.items() if value]
    name_key = normalized_name(candidate.name)
    country = candidate.location.get("country_code")
    clauses = []
    if domain:
        clauses.append({"domain": domain})
    if keys:
        clauses.append({"external_keys": {"$in": keys}})
    if name_key and country:
        clauses.append({"name_normalized": name_key, "location.country_code": country})
    previous = database.companies.find_one({"$or": clauses}) if clauses else None
    supplied = candidate.model_dump(exclude={"source_name", "source_url", "source_type", "demo"})
    fields = [k for k, v in supplied.items() if v not in (None, [], {})]
    source = source_record(candidate, fields)
    if previous:
        changes = {}
        for field in fields:
            if field in {"external_ids", "other_urls", "industry", "sub_industries", "business_model", "founders", "executives"}:
                continue
            if field in {"location", "employees", "funding"}:
                merged = dict(previous.get(field) or {})
                for key, value in supplied[field].items():
                    if value is not None and merged.get(key) in (None, ""):
                        merged[key] = value
                changes[field] = merged
            elif previous.get(field) in (None, "", []):
                changes[field] = supplied[field]
        changes["updated_at"] = now()
        for field in ("founders", "executives", "industry", "sub_industries", "business_model", "other_urls"):
            if supplied.get(field):
                changes[field] = list({str(item): item for item in (previous.get(field) or []) + supplied[field]}.values())
        merged_doc = {**previous, **changes}
        changes.update(score_company(merged_doc))
        database.companies.update_one({"_id": previous["_id"]}, {"$set": changes, "$addToSet": {"sources": source, "external_keys": {"$each": keys}}})
        persist_related(previous["_id"], candidate, source)
        return str(previous["_id"]), False
    document = {**supplied, "domain": domain, "external_keys": keys, "name_normalized": name_key,
                "sources": [source], "demo": candidate.demo, "is_demo": candidate.demo, "first_discovered_at": now(), "last_enriched_at": now(),
                "last_verified_at": now(), "created_at": now(), "updated_at": now()}
    document.update(score_company(document))
    result = database.companies.insert_one(document)
    persist_related(result.inserted_id, candidate, source)
    return str(result.inserted_id), True


async def run_discovery(job_id: str, criteria: SearchCriteria):
    jobs = db().discovery_jobs
    jobs.update_one({"_id": job_id}, {"$set": {"status": "running", "stage": "Searching sources", "progress": 10}})
    found = 0
    inserted = 0
    errors = []
    providers = live_providers()
    for index, provider in enumerate(providers):
        try:
            candidates = await provider.search(criteria)
            found += len(candidates)
            jobs.update_one({"_id": job_id}, {"$set": {"stage": f"Normalizing {provider.name}", "found": found, "progress": 20 + int(index / max(1, len(providers)) * 60)}})
            for candidate in candidates:
                try:
                    _, created = upsert_candidate(candidate)
                    inserted += int(created)
                except Exception as exc:
                    log.exception("Candidate ingestion failed")
                    errors.append(f"{provider.name}: candidate rejected ({type(exc).__name__})")
        except Exception as exc:
            log.exception("Provider %s failed", provider.name)
            errors.append(f"{provider.name}: {type(exc).__name__}")
    jobs.update_one({"_id": job_id}, {"$set": {"status": "completed", "stage": "Complete", "progress": 100, "found": found, "inserted": inserted, "errors": errors, "completed_at": now()}})
