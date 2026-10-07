import logging
from datetime import datetime, timedelta, timezone
from pymongo import ReturnDocument
from .config import settings
from .database import db
from .models import CompanyCandidate, SearchCriteria, now
from .normalize import domain_from_url, normalized_name, safe_public_url, source_record
from .providers import live_providers, enrichment_providers
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
    if not candidate.name.strip() or not candidate.source_name.strip() or not candidate.source_url.startswith("https://") or not safe_public_url(candidate.source_url):
        raise ValueError("A real company candidate needs a name and a public HTTPS source")
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
    if candidate.linkedin_url:
        clauses.append({"linkedin_url": candidate.linkedin_url})
    previous = database.companies.find_one({"$or": clauses}) if clauses else None
    match_classification = "exact" if previous else "none"
    city = candidate.location.get("city")
    if not previous and name_key and country and city:
        matches = list(database.companies.find({"name_normalized": name_key,
            "location.country_code": country, "location.city": city}).limit(2))
        if len(matches) == 1:
            previous, match_classification = matches[0], "high confidence"
    if not previous and name_key and country and len(name_key.split()) >= 2:
        matches = list(database.companies.find({"name_normalized": name_key,
            "location.country_code": country}).limit(2))
        if len(matches) == 1 and (domain or matches[0].get("domain")) and (not domain or not matches[0].get("domain") or domain == matches[0]["domain"]):
            previous, match_classification = matches[0], "high confidence"
    possible_matches = []
    if not previous and name_key and country:
        possible_matches = [str(x["_id"]) for x in database.companies.find({
            "name_normalized": name_key, "location.country_code": country}, {"_id": 1}).limit(5)]
        if possible_matches:
            match_classification = "possible match"
    supplied = candidate.model_dump(exclude={"source_name", "source_url", "source_type"})
    fields = [k for k, v in supplied.items() if v not in (None, [], {})]
    source = source_record(candidate, fields)
    def prefer_incoming(old: dict) -> bool:
        old_confidence = old.get("confidence", 0.5)
        if source["confidence"] > old_confidence:
            return True
        collected = old.get("collected_at")
        if source["confidence"] == old_confidence and isinstance(collected, datetime):
            collected = collected.replace(tzinfo=collected.tzinfo or timezone.utc)
            return collected < now() - timedelta(days=settings.refresh_days)
        return False
    def evidence(value):
        return {"value": value, "provider": candidate.source_name, "url": candidate.source_url,
                "collected_at": source["collected_at"], "confidence": source["confidence"],
                "classification": "verified"}
    incoming_evidence = {}
    for field in fields:
        value = supplied[field]
        if isinstance(value, dict):
            for subfield, subvalue in value.items():
                if subvalue not in (None, "", [], {}):
                    incoming_evidence[f"{field}.{subfield}"] = evidence(subvalue)
        else:
            incoming_evidence[field] = evidence(value)
    if previous:
        changes = {}
        field_evidence = dict(previous.get("field_evidence") or {})
        conflicts = list(previous.get("field_conflicts") or [])
        for field in fields:
            if field in {"external_ids", "other_urls", "industry", "sub_industries", "business_model", "founders", "executives"}:
                continue
            if field in {"location", "employees", "funding", "technology_signals", "filing_signals"}:
                merged = dict(previous.get(field) or {})
                for key, value in supplied[field].items():
                    path = f"{field}.{key}"
                    if value is None:
                        continue
                    if merged.get(key) in (None, ""):
                        merged[key] = value
                        if path in incoming_evidence:
                            field_evidence[path] = incoming_evidence[path]
                    elif merged.get(key) != value and path in incoming_evidence:
                        old_value = merged.get(key)
                        old = field_evidence.get(path, {})
                        if prefer_incoming(old):
                            merged[key] = value
                            field_evidence[path] = incoming_evidence[path]
                        conflict = {"field": path, "values": [old.get("value", old_value), value],
                                    "sources": [old.get("provider"), candidate.source_name]}
                        if conflict not in conflicts:
                            conflicts.append(conflict)
                    elif path in incoming_evidence and path not in field_evidence:
                        field_evidence[path] = incoming_evidence[path]
                changes[field] = merged
            elif previous.get(field) in (None, "", []):
                changes[field] = supplied[field]
                if field in incoming_evidence:
                    field_evidence[field] = incoming_evidence[field]
            elif previous.get(field) != supplied[field] and field in incoming_evidence:
                old = field_evidence.get(field, {})
                if prefer_incoming(old):
                    changes[field] = supplied[field]
                    field_evidence[field] = incoming_evidence[field]
                conflict = {"field": field, "values": [old.get("value", previous.get(field)), supplied[field]],
                            "sources": [old.get("provider"), candidate.source_name]}
                if conflict not in conflicts:
                    conflicts.append(conflict)
            elif field in incoming_evidence and field not in field_evidence:
                field_evidence[field] = incoming_evidence[field]
        changes["updated_at"] = now()
        changes["last_enriched_at"] = now()
        changes["last_verified_at"] = now()
        changes["external_ids"] = {**(previous.get("external_ids") or {}), **(supplied.get("external_ids") or {})}
        for path, item in incoming_evidence.items():
            if path not in field_evidence and (path.startswith("external_ids.") or path in {"founders", "executives", "other_urls", "industry", "sub_industries", "business_model"}):
                field_evidence[path] = item
        if domain and not previous.get("domain"):
            changes["domain"] = domain
        for field in ("founders", "executives", "industry", "sub_industries", "business_model", "other_urls"):
            if supplied.get(field):
                changes[field] = list({str(item): item for item in (previous.get(field) or []) + supplied[field]}.values())
        changes["field_evidence"] = field_evidence
        changes["field_conflicts"] = conflicts[-50:]
        changes["match_classification"] = match_classification
        changes["sources"] = [s for s in previous.get("sources", []) if not (s.get("source_name") == source["source_name"] and s.get("source_url") == source["source_url"])] + [source]
        merged_doc = {**previous, **changes}
        changes.update(score_company(merged_doc))
        database.companies.update_one({"_id": previous["_id"]}, {"$set": changes, "$addToSet": {"external_keys": {"$each": keys}}})
        persist_related(previous["_id"], candidate, source)
        return str(previous["_id"]), False
    document = {**supplied, "domain": domain, "external_keys": keys, "name_normalized": name_key,
                "sources": [source], "field_evidence": incoming_evidence, "field_conflicts": [],
                "match_classification": match_classification, "possible_matches": possible_matches,
                "first_discovered_at": now(), "last_enriched_at": now(),
                "last_verified_at": now(), "created_at": now(), "updated_at": now()}
    document.update(score_company(document))
    result = database.companies.insert_one(document)
    persist_related(result.inserted_id, candidate, source)
    return str(result.inserted_id), True


async def run_discovery(job_id: str, criteria: SearchCriteria):
    jobs = db().discovery_jobs
    jobs.update_one({"_id": job_id}, {"$set": {"status": "running", "stage": "Searching sources", "progress": 10}})
    found = 0
    valid = 0
    rejected = 0
    duplicates = 0
    inserted = 0
    errors = []
    providers = live_providers()
    provider_status = {}
    enriched = 0
    seen_ids = set()
    for index, provider in enumerate(providers):
        if getattr(provider, "requires_name", False) and not criteria.query.strip():
            provider_status[provider.name] = {"status": "skipped", "reason": "Company-name lookup only"}
            continue
        try:
            candidates = await provider.search(criteria)
            provider_status[provider.name] = {"status": "completed", "candidates": len(candidates)}
            found += len(candidates)
            jobs.update_one({"_id": job_id}, {"$set": {"stage": f"Normalizing {provider.name}", "found": found, "progress": 20 + int(index / max(1, len(providers)) * 60)}})
            for candidate in candidates:
                try:
                    company_id, created = upsert_candidate(candidate)
                    valid += 1
                    seen_ids.add(company_id)
                    inserted += int(created)
                    duplicates += int(not created)
                except Exception as exc:
                    rejected += 1
                    log.exception("Candidate ingestion failed")
                    errors.append(f"{provider.name}: candidate rejected ({type(exc).__name__})")
        except Exception as exc:
            log.exception("Provider %s failed", provider.name)
            errors.append(f"{provider.name}: {type(exc).__name__}")
            provider_status[provider.name] = {"status": "failed", "error": type(exc).__name__}
    jobs.update_one({"_id": job_id}, {"$set": {"stage": "Enriching sourced profiles", "progress": 85, "provider_status": provider_status}})
    from bson import ObjectId
    enrichers = enrichment_providers()
    for provider in enrichers:
        provider_status[provider.name] = {"status": "skipped", "enriched": 0}
    for identifier in seen_ids:
        company = db().companies.find_one({"_id": ObjectId(identifier)})
        if not company:
            continue
        for provider in enrichers:
            try:
                supplement = await provider.enrich(company)
                if supplement:
                    upsert_candidate(supplement)
                    enriched += 1
                    provider_status[provider.name] = {"status": "completed", "enriched": provider_status[provider.name].get("enriched", 0) + 1}
            except Exception as exc:
                log.exception("Enrichment provider %s failed", provider.name)
                errors.append(f"{provider.name}: {type(exc).__name__}")
                provider_status[provider.name] = {"status": "failed", "error": type(exc).__name__}
    missing = {"employees": 0, "funding": 0, "industry": 0, "website": 0}
    for identifier in seen_ids:
        company = db().companies.find_one({"_id": ObjectId(identifier)}) or {}
        missing["employees"] += int(not company.get("employees"))
        missing["funding"] += int((company.get("funding") or {}).get("total_amount_usd") is None)
        missing["industry"] += int(not company.get("industry"))
        missing["website"] += int(not company.get("website"))
    jobs.update_one({"_id": job_id}, {"$set": {"status": "completed", "stage": "Complete", "progress": 100,
        "found": found, "valid_candidates": valid, "duplicates": duplicates, "rejected_candidates": rejected,
        "inserted": inserted, "unique_companies": len(seen_ids), "enriched": enriched, "missing_data": missing,
        "provider_status": provider_status, "errors": errors, "completed_at": now()}})


async def run_enrichment(job_id: str, company_id: str):
    """Refresh only adapters supported by identifiers already sourced for this company."""
    from bson import ObjectId
    jobs = db().discovery_jobs
    company = db().companies.find_one({"_id": ObjectId(company_id)})
    if not company:
        jobs.update_one({"_id": job_id}, {"$set": {"status": "failed", "stage": "Company unavailable", "progress": 100}})
        return
    jobs.update_one({"_id": job_id}, {"$set": {"status": "running", "stage": "Refreshing sourced profiles", "progress": 25}})
    statuses, errors, enriched = {}, [], 0
    for provider in enrichment_providers():
        try:
            supplement = await provider.enrich(company)
            if supplement:
                upsert_candidate(supplement)
                enriched += 1
                statuses[provider.name] = {"status": "completed", "enriched": 1}
            else:
                statuses[provider.name] = {"status": "skipped", "enriched": 0}
        except Exception as exc:
            log.exception("Enrichment provider %s failed", provider.name)
            statuses[provider.name] = {"status": "failed", "error": type(exc).__name__}
            errors.append(f"{provider.name}: {type(exc).__name__}")
    jobs.update_one({"_id": job_id}, {"$set": {"status": "completed", "stage": "Complete", "progress": 100,
        "enriched": enriched, "provider_status": statuses, "errors": errors, "completed_at": now()}})
