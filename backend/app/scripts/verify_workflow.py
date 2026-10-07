"""Atlas-backed workflow check using existing sourced companies only."""
import uuid
from fastapi.testclient import TestClient
from .. import main as api
from ..database import db, initialize

def main():
    initialize()
    user = "workflow-check-" + uuid.uuid4().hex
    previous_user = api.USER_ID
    api.USER_ID = user
    database = db()
    try:
        with TestClient(api.app) as client:
            assert client.get("/api/health").json()["ok"]
            empty = client.post("/api/companies/search", json={"page_size": 1})
            assert empty.status_code == 200
            company = database.companies.find_one({"sources.0": {"$exists": True}})
            if not company:
                print("Atlas workflow: empty database search and initialization passed; company actions await sourced records")
                return
            company_id = str(company["_id"])
            filters = {"query": company["name"], "page_size": 20}
            results = client.post("/api/companies/search", json=filters)
            assert results.status_code == 200 and results.json()["total"] >= 1
            assert client.get("/api/companies/" + company_id).status_code == 200
            assert client.post("/api/saved-companies", json={"company_id": company_id, "notes": "Workflow check"}).status_code == 200
            assert client.post("/api/outreach", json={"company_id": company_id, "status": "researching"}).status_code == 200
            saved_search = client.post("/api/searches", json={"name": "Workflow check", "criteria": filters})
            assert saved_search.status_code == 200
            assert client.get("/api/searches/" + saved_search.json()["id"]).status_code == 200
            assert client.get("/api/export", params={"ids": company_id}).status_code == 200
            assert client.get("/api/dashboard").status_code == 200
            print("Atlas workflow: sourced search, profile, save, outreach, saved search, export and dashboard passed")
    finally:
        database.saved_companies.delete_many({"user_id": user})
        database.outreach.delete_many({"user_id": user})
        database.searches.delete_many({"user_id": user})
        api.USER_ID = previous_user

if __name__ == "__main__":
    main()
