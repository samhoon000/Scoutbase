from fastapi.testclient import TestClient
from app.main import app
from app.models import CompanyCandidate
from app.pipeline import upsert_candidate
from app.pipeline import run_discovery
from app.database import db
from app import database
from app.config import settings
from app.normalize import domain_from_url, normalized_name
from app.scoring import score_company
import pytest
import asyncio
from unittest.mock import patch


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    import mongomock
    mock = mongomock.MongoClient()
    monkeypatch.setattr(database, "client", lambda: mock)
    yield


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


def test_end_to_end_sourced_workflow():
    with TestClient(app) as client:
        upsert_candidate(CompanyCandidate(name="Sourced Workflow Company", industry=["E-commerce"],
            location={"country_code": "GB"}, source_name="Wikidata",
            source_url="https://www.wikidata.org/wiki/Q123", source_type="open dataset"))
        listing = client.post("/api/companies/search", json={"country_code": "GB", "industry": "E-commerce", "page_size": 20}).json()
        assert listing["total"] > 0
        company = listing["items"][0]
        assert company["sources"][0]["source_type"] == "open dataset"
        assert client.get(f"/api/companies/{company['id']}").status_code == 200
        assert client.post("/api/saved-companies", json={"company_id": company["id"]}).status_code == 200
        assert client.get("/api/dashboard").json()["saved"] >= 1
        assert client.post("/api/outreach", json={"company_id": company["id"], "status": "contacted"}).status_code == 200
        assert client.get("/api/export", params={"ids": company["id"]}).status_code == 200
        exported = client.get("/api/export", params={"ids": company["id"]}).text
        assert "Contact Person" in exported and "Data Confidence" in exported
        assert client.delete(f"/api/saved-companies/{company['id']}").status_code == 200


def test_growth_filter_uses_scored_signal():
    from app.models import now
    with TestClient(app) as client:
        upsert_candidate(CompanyCandidate(name="Funded Fixture Company", industry=["SaaS"],
            funding={"total_amount_usd": 1_000_000, "last_funding_date": now()},
            source_name="Wikidata", source_url="https://www.wikidata.org/wiki/Q124", source_type="open dataset"))
        results = client.post("/api/companies/search", json={"growth_score_min": 20, "page_size": 100}).json()
        assert results["total"] > 0
        assert all(item["signals"]["growth_score"] >= 20 for item in results["items"])


def test_filter_first_multiselect_ranges_and_empty_results():
    with TestClient(app) as client:
        for name, country, industry in (("Company One", "GB", "E-commerce"), ("Company Two", "US", "SaaS"), ("Company Three", "DE", "Logistics")):
            upsert_candidate(CompanyCandidate(name=name, industry=[industry], location={"country_code": country},
                employees={"exact": 42}, source_name="Wikidata",
                source_url="https://www.wikidata.org/wiki/" + name.replace(" ", ""), source_type="open dataset"))
        options = client.get("/api/filter-options").json()
        assert "GB" in options["countries"]
        assert "E-commerce" in options["industries"]
        result = client.post("/api/companies/search", json={
            "countries": ["GB", "US"], "industries": ["ecommerce", "SaaS"],
            "employees_min": 1, "employees_max": 10000, "page_size": 100,
        }).json()
        assert result["total"] > 0
        assert all(x["location"]["country_code"] in {"GB", "US"} for x in result["items"])
        assert all(any(i.lower() in {"e-commerce", "saas"} for i in x["industry"]) for x in result["items"])
        assert all((x["employees"].get("exact") or x["employees"].get("min")) <= 10000 for x in result["items"])
        assert client.post("/api/companies/search", json={"countries": ["ZZ"]}).json()["total"] == 0
        assert client.post("/api/companies/search", json={"employees_min": 50, "employees_max": 5}).status_code == 422


def test_saved_search_reruns_full_criteria():
    with TestClient(app) as client:
        criteria = {"countries": ["GB", "US"], "industries": ["Fintech", "SaaS"], "funding_min": 1,
                    "score_min": 30, "sort": "founded_year", "order": "asc"}
        original = client.post("/api/companies/search", json=criteria).json()
        saved = client.post("/api/searches", json={"name": "Filtered prospects", "criteria": criteria}).json()
        loaded = client.get(f"/api/searches/{saved['id']}").json()
        rerun = client.post("/api/companies/search", json=loaded["criteria"]).json()
        assert loaded["criteria"]["countries"] == criteria["countries"]
        assert loaded["criteria"]["industries"] == criteria["industries"]
        assert [x["id"] for x in rerun["items"]] == [x["id"] for x in original["items"]]
        assert client.patch(f"/api/searches/{saved['id']}", json={"name": "Renamed"}).json()["name"] == "Renamed"
        assert client.delete(f"/api/searches/{saved['id']}").status_code == 200
        assert client.get(f"/api/searches/{saved['id']}").status_code == 404


def test_unsupported_evidence_filters_do_not_fabricate_matches():
    with TestClient(app) as client:
        options = client.get("/api/filter-options").json()
        assert options["coverage"]["opportunity_evidence.high_transaction_volume"] == 0
        assert client.post("/api/companies/search", json={"high_transaction_volume": True}).json()["total"] == 0


def test_exact_headcount_range_and_live_filter_only_search():
    from unittest.mock import AsyncMock
    with TestClient(app) as client:
        upsert_candidate(CompanyCandidate(name="Exact Headcount Company", employees={"exact": 42},
            industry=["SaaS"], location={"country_code": "GB"}, source_name="Wikidata",
            source_url="https://www.wikidata.org/wiki/Q125", source_type="open dataset"))
        matching = client.post("/api/companies/search", json={"employees_min": 40, "employees_max": 45, "page_size": 100}).json()
        assert any(x["name"] == "Exact Headcount Company" for x in matching["items"])
        assert client.post("/api/companies/search", json={"query": "Exact Headcount Company", "employees_min": 43}).json()["total"] == 0
        with patch("app.main.run_discovery", new_callable=AsyncMock):
            discovery = client.post("/api/companies/discover", json={"countries": ["GB"], "industries": ["SaaS"]})
        assert discovery.status_code == 200
        assert discovery.json()["job_id"]


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
        db().discovery_jobs.insert_one({"_id": "test-job", "status": "queued"})
        with patch("app.pipeline.live_providers", return_value=[Broken(), Working()]):
            asyncio.run(run_discovery("test-job", __import__("app.models", fromlist=["SearchCriteria"]).SearchCriteria(query="Real")))
        result = db().discovery_jobs.find_one({"_id": "test-job"})
        assert result["status"] == "completed"
        assert result["inserted"] == 1
        assert len(result["errors"]) == 1


def test_empty_database_and_source_validation():
    from app.main import list_companies
    from app.models import SearchCriteria
    with TestClient(app):
        assert list_companies(SearchCriteria())["total"] == 0
        with pytest.raises(ValueError):
            upsert_candidate(CompanyCandidate(name="Unverified", source_name="Unknown", source_url="invalid"))
        assert db().companies.count_documents({}) == 0


def test_higher_priority_source_wins_and_conflict_is_recorded():
    with TestClient(app):
        first = CompanyCandidate(name="Mergeable", website="https://mergeable.example", employees={"exact": 30},
            source_name="Community", source_url="https://community.example/mergeable", source_type="open dataset")
        second = CompanyCandidate(name="Mergeable", website="https://mergeable.example", employees={"exact": 40},
            source_name="Official", source_url="https://official.example/mergeable", source_type="official API")
        identifier, _ = upsert_candidate(first)
        upsert_candidate(second)
        record = db().companies.find_one({"domain": "mergeable.example"})
        assert str(record["_id"]) == identifier
        assert record["employees"]["exact"] == 40
        assert record["field_evidence"]["employees.exact"]["provider"] == "Official"
        assert any(item["field"] == "employees.exact" for item in record["field_conflicts"])


def test_stale_equal_quality_source_can_refresh_value():
    from datetime import timedelta
    from app.models import now
    with TestClient(app):
        first = CompanyCandidate(name="Refreshable Company", website="https://refreshable.example",
            employees={"exact": 30}, source_name="Source A", source_url="https://source-a.example/company",
            source_type="open dataset")
        identifier, _ = upsert_candidate(first)
        original = db().companies.find_one({"_id": __import__("bson").ObjectId(identifier)})
        evidence = original["field_evidence"]
        evidence["employees.exact"]["collected_at"] = now() - timedelta(days=60)
        db().companies.update_one({"_id": original["_id"]}, {"$set": {"field_evidence": evidence}})
        second = CompanyCandidate(name="Refreshable Company", website="https://refreshable.example",
            employees={"exact": 40}, source_name="Source B", source_url="https://source-b.example/company",
            source_type="open dataset")
        upsert_candidate(second)
        record = db().companies.find_one({"_id": __import__("bson").ObjectId(identifier)})
        assert record["employees"]["exact"] == 40
        assert record["field_evidence"]["employees.exact"]["provider"] == "Source B"


def test_sec_enrichment_does_not_fabricate_funding(monkeypatch):
    from app.providers import SECProvider
    monkeypatch.setattr(settings, "sec_user_agent", "ScoutBase test@example.com")
    provider = SECProvider()
    async def payload(*args, **kwargs):
        return {"cik": 320193, "name": "Apple Inc.", "sicDescription": "Electronic Computers",
            "filings": {"recent": {"form": ["10-K"], "filingDate": ["2026-01-01"], "accessionNumber": ["abc"]}}}
    provider.get_json = payload
    result = asyncio.run(provider.enrich({"name": "Apple", "external_ids": {"sec_cik": "0000320193"}}))
    assert result is not None
    assert result.filing_signals["recent_filings"][0]["form"] == "10-K"
    assert result.funding == {}


def test_sec_waits_for_declared_contact(monkeypatch):
    from app.providers import SECProvider
    from app.integrations.sec import SECService
    monkeypatch.setattr(settings, "sec_user_agent", "ScoutBase/0.1")
    assert asyncio.run(SECProvider().enrich({"name": "Apple", "external_ids": {"sec_cik": "0000320193"}})) is None
    assert asyncio.run(SECService(settings.sec_user_agent).check()) == "needs_contact_user_agent"


def test_ambiguous_same_name_is_possible_match_not_merged():
    with TestClient(app):
        first, _ = upsert_candidate(CompanyCandidate(name="Shared Brand", location={"country_code": "US"},
            source_name="A", source_url="https://a.example/shared"))
        second, created = upsert_candidate(CompanyCandidate(name="Shared Brand", location={"country_code": "US"},
            source_name="B", source_url="https://b.example/shared"))
        assert created and first != second
        assert first in db().companies.find_one({"_id": __import__("bson").ObjectId(second)})["possible_matches"]


def test_sourced_website_and_exact_name_country_can_merge():
    with TestClient(app):
        legal_id, _ = upsert_candidate(CompanyCandidate(name="Northstar OpCo LLC", location={"country_code": "US"},
            external_ids={"gleif": "TESTLEI"}, source_name="GLEIF", source_url="https://gleif.example/test"))
        brand_id, created = upsert_candidate(CompanyCandidate(name="Northstar OpCo", website="https://northstar.example",
            location={"country_code": "US"}, external_ids={"wikidata": "Q123"},
            source_name="Wikidata", source_url="https://wikidata.example/Q123", source_type="open dataset"))
        assert not created and legal_id == brand_id
        assert len(db().companies.find_one({"domain": "northstar.example"})["sources"]) == 2


def test_provider_cache_reuses_response_without_network():
    from datetime import timedelta
    from app.models import now
    from app.providers import GLEIFProvider
    import hashlib, json
    url = "https://api.gleif.org/api/v1/lei-records"
    params = {"filter[entity.legalName]": "Cached"}
    key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
    with TestClient(app):
        db().provider_cache.insert_one({"provider": "GLEIF", "key": key, "request_hash": key,
            "response": {"data": []}, "created_at": now(), "expires_at": now() + timedelta(days=1)})
        assert asyncio.run(GLEIFProvider().get_json(url, params)) == {"data": []}
        assert db().api_usage.find_one({"provider": "GLEIF"})["cache_hits"] == 1


@pytest.mark.parametrize("status,expected_counter", [(401, "failures"), (429, "rate_limits")])
def test_provider_auth_and_rate_limit_are_tracked(monkeypatch, status, expected_counter):
    import httpx
    from app.providers import GLEIFProvider
    original_client = httpx.AsyncClient
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Retry-After": "120"})
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.source_providers.base.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs))
    with TestClient(app):
        provider = GLEIFProvider()
        provider.interval = 0
        with pytest.raises((RuntimeError, httpx.HTTPStatusError)):
            asyncio.run(provider.get_json("https://api.gleif.org/test"))
        assert db().api_usage.find_one({"provider": "GLEIF"})[expected_counter] == 1
        if status == 429:
            with pytest.raises(RuntimeError):
                asyncio.run(provider.get_json("https://api.gleif.org/test"))
            assert len(calls) == 1


def test_provider_rejects_malformed_json(monkeypatch):
    import httpx
    from app.providers import GLEIFProvider
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="not-json"))
    monkeypatch.setattr("app.source_providers.base.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs))
    with TestClient(app):
        provider = GLEIFProvider()
        provider.interval = 0
        with pytest.raises(ValueError):
            asyncio.run(provider.get_json("https://api.gleif.org/bad"))
        assert db().api_usage.find_one({"provider": "GLEIF"})["malformed_responses"] == 1


def test_provider_retries_timeout_then_recovers(monkeypatch):
    import httpx
    from app.providers import GLEIFProvider
    original_client = httpx.AsyncClient
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("temporary timeout")
        return httpx.Response(200, json={"data": []})
    monkeypatch.setattr("app.source_providers.base.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    with TestClient(app):
        provider = GLEIFProvider()
        provider.interval = 0
        assert asyncio.run(provider.get_json("https://api.gleif.org/retry")) == {"data": []}
        assert len(calls) == 2
        usage = db().api_usage.find_one({"provider": "GLEIF"})
        assert usage["requests"] == 2 and usage["failures"] == 1 and usage["successes"] == 1
