"""Atlas-backed workflow check. Uses a temporary user and removes its records."""
import uuid
from bson import ObjectId
from fastapi.testclient import TestClient
from .. import main as api
from ..database import db, initialize
from ..models import CompanyCandidate
from ..pipeline import upsert_candidate


def main():
    initialize()
    user = "workflow-check-" + uuid.uuid4().hex
    api.USER_ID = user
    database = db()
    probe_id = None
    try:
        probe_name = "ProspectIQ Integration Probe " + uuid.uuid4().hex[:12]
        candidate = CompanyCandidate(name=probe_name, location={"country_code": "US"},
            external_ids={"integration_probe": user}, source_name="Integration test", source_url="demo://atlas-integration", source_type="demo", demo=True)
        probe_id, created = upsert_candidate(candidate)
        assert created and database.companies.find_one({"_id": ObjectId(probe_id)})
        candidate.description = "Updated integration test record"
        same_id, created_again = upsert_candidate(candidate)
        assert not created_again and same_id == probe_id
        assert database.companies.find_one({"name_normalized": database.companies.find_one({"_id": ObjectId(probe_id)})["name_normalized"]})["description"] == candidate.description
        with TestClient(api.app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200 and response.json()["ok"]
            company = database.companies.find_one({"demo": True, "funding.total_amount_usd": {"$gte": 1_000_000}})
            assert company is not None
            company_id = str(company["_id"])
            country = company["location"]["country_code"]
            industry = company["industry"][0]
            minimum_employees = company["employees"]["min"]
            minimum_funding = company["funding"]["total_amount_usd"]
            filters = {"country_code": country, "industry": industry, "employees_min": minimum_employees,
                       "funding_min": minimum_funding, "sort": "prospect_score", "order": "desc", "page_size": 2}
            search = client.post("/api/companies/search", json=filters)
            assert search.status_code == 200
            results = search.json()
            assert results["total"] >= 1
            assert any(c["id"] == company_id for c in results["items"])
            scores = [c["prospect_score"] for c in results["items"]]
            assert scores == sorted(scores, reverse=True)
            assert client.get("/api/companies", params={"page": 2, "page_size": 5}).status_code == 200
            assert client.get(f"/api/companies/{company_id}").json()["demo"] is True
            assert client.post("/api/saved-companies", json={"company_id": company_id, "notes": "Test note"}).status_code == 200
            assert client.post("/api/saved-companies", json={"company_id": company_id, "notes": "Updated test note"}).status_code == 200
            saved = client.get("/api/saved-companies").json()
            assert len(saved) == 1 and saved[0]["notes"] == "Updated test note"
            outreach = client.post("/api/outreach", json={"company_id": company_id, "status": "researching"})
            assert outreach.status_code == 200
            outreach_id = outreach.json()["id"]
            updated = client.patch(f"/api/outreach/{outreach_id}", json={"company_id": company_id, "status": "contacted"})
            assert updated.status_code == 200 and updated.json()["status"] == "contacted"
            history = client.post("/api/searches", json={"name": "Integration check", "criteria": filters})
            assert history.status_code == 200
            assert len(client.get("/api/searches").json()) == 1
            assert client.get("/api/export", params={"ids": company_id}).status_code == 200
            assert client.get("/api/dashboard").json()["saved"] >= 1
        print("Atlas workflow: search, filters, sorting, pagination, detail, save/update, outreach/update, history, export passed")
        print("Atlas company insert, read, update, and indexed identity query passed")
    except Exception as error:
        print(f"Atlas workflow failed: {type(error).__name__}")
        raise SystemExit(1)
    finally:
        database.saved_companies.delete_many({"user_id": user})
        database.outreach.delete_many({"user_id": user})
        database.searches.delete_many({"user_id": user})
        if probe_id:
            probe_oid = ObjectId(probe_id)
            database.sources.delete_many({"company_id": probe_oid})
            database.people.delete_many({"company_id": probe_oid})
            database.funding_rounds.delete_many({"company_id": probe_oid})
            database.companies.delete_one({"_id": probe_oid})


if __name__ == "__main__":
    main()
