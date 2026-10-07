from fastapi.testclient import TestClient
from app.main import app
from app.models import CompanyCandidate
from app.pipeline import upsert_candidate
from app.pipeline import run_discovery
from app.database import db
from app.database import client as mongo_client
from app.normalize import domain_from_url, normalized_name
from app.scoring import score_company
import pytest
import asyncio
from unittest.mock import patch


@pytest.fixture(autouse=True)
def fresh_demo_database():
    mongo_client.cache_clear()
    yield
    mongo_client.cache_clear()


def test_normalization():
    assert normalized_name("Acme Technologies Ltd.") == "acme"
    assert domain_from_url("https://www.example.org/path") == "example.org"
    assert domain_from_url("http://localhost/admin") is None


def test_deduplication_by_domain_and_sources():
    with TestClient(app):
        first = CompanyCandidate(name="Example Ltd", website="https://www.example-test.org", location={"country_code": "GB"}, source_name="A", source_url="https://a.example")
        second = CompanyCandidate(name="Example Corporation", website="https://example-test.org", description="Verified description", location={"country_code": "GB"}, source_name="B", source_url="https://b.example")
        id1, created1 = upsert_candidate(first)
        id2, created2 = upsert_candidate(second)
        assert created1 and not created2 and id1 == id2
        record = db().companies.find_one({"domain": "example-test.org"})
        assert record["description"] == "Verified description"
        assert len(record["sources"]) == 2


def test_end_to_end_demo_workflow():
    with TestClient(app) as client:
        listing = client.post("/api/companies/search", json={"country_code": "GB", "industry": "E-commerce", "page_size": 20}).json()
        assert listing["total"] > 0
        company = listing["items"][0]
        assert company["demo"] is True
        assert company["sources"][0]["source_type"] == "demo"
        assert client.get(f"/api/companies/{company['id']}").status_code == 200
        assert client.post("/api/saved-companies", json={"company_id": company["id"]}).status_code == 200
        assert client.get("/api/dashboard").json()["saved"] >= 1
        assert client.post("/api/outreach", json={"company_id": company["id"], "status": "contacted"}).status_code == 200
        assert client.get("/api/export", params={"ids": company["id"]}).status_code == 200
        assert client.delete(f"/api/saved-companies/{company['id']}").status_code == 200


def test_unknown_funding_does_not_increase_funding_score():
    result = score_company({"name": "Unknown", "industry": ["SaaS"], "funding": {"total_amount_usd": None}})
    assert result["signals"]["funding_score"] == 0
    assert not any("funding" in reason.lower() for reason in result["prospect_reason"])


def test_discovery_continues_after_provider_failure():
    class Broken:
        name = "Broken"
        async def search(self, criteria):
            raise RuntimeError("unavailable")
    class Working:
        name = "Working"
        async def search(self, criteria):
            return [CompanyCandidate(name="Real Test Company", location={"country_code": "US"}, source_name="Working", source_url="https://example.org/source")]
    with TestClient(app):
        db().jobs.insert_one({"_id": "test-job", "status": "queued"})
        with patch("app.pipeline.live_providers", return_value=[Broken(), Working()]):
            asyncio.run(run_discovery("test-job", __import__("app.models", fromlist=["SearchCriteria"]).SearchCriteria(query="Real")))
        result = db().jobs.find_one({"_id": "test-job"})
        assert result["status"] == "completed"
        assert result["inserted"] == 1
        assert len(result["errors"]) == 1
