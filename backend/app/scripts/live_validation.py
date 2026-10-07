"""Run four bounded real-source discovery checks against the configured MongoDB."""
import asyncio
import json
import uuid
from ..database import db, initialize
from ..main import mongo_filter
from ..models import SearchCriteria, now
from ..pipeline import run_discovery

CASES = (
    ("A", {"countries": ["DE"], "industries": ["E-commerce"], "employees_min": 10, "employees_max": 100}),
    ("B", {"countries": ["GB"], "industries": ["SaaS"], "employees_min": 10, "employees_max": 100}),
    ("C", {"countries": ["US"], "industries": ["E-commerce"], "employees_min": 10, "employees_max": 100}),
    ("D", {"industries": ["E-commerce"]}),
)

def run():
    initialize()
    database = db()
    for label, payload in CASES:
        criteria = SearchCriteria(**payload)
        before = database.companies.count_documents(mongo_filter(criteria))
        discovery = criteria.model_copy(update={
            "country_code": criteria.countries[0] if criteria.countries else None,
            "industry": criteria.industries[0] if criteria.industries else None,
        })
        job_id = "live-validation-" + uuid.uuid4().hex
        database.discovery_jobs.insert_one({"_id": job_id, "status": "queued", "criteria": criteria.model_dump(),
            "created_at": now(), "errors": [], "existing": before})
        asyncio.run(run_discovery(job_id, discovery))
        job = database.discovery_jobs.find_one({"_id": job_id}) or {}
        after = database.companies.count_documents(mongo_filter(criteria))
        result = {"case": label, "filters": payload, "provider_queried": [name for name, state in (job.get("provider_status") or {}).items() if state.get("status") in {"completed", "failed"}],
            "raw_candidates": job.get("found", 0), "valid_candidates": job.get("valid_candidates", 0),
            "duplicates": job.get("duplicates", 0), "unique_real_companies": job.get("unique_companies", 0),
            "enriched_companies": job.get("enriched", 0), "rejected_candidates": job.get("rejected_candidates", 0),
            "provider_failures": job.get("errors", []), "provider_coverage": job.get("provider_status", {}),
            "missing_data": job.get("missing_data", {}), "matching_before": before, "final_result_count": after}
        print(json.dumps(result, default=str), flush=True)

if __name__ == "__main__":
    run()
