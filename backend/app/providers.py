"""Replaceable, source-specific adapters. No page scraping or inferred facts."""
import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import timedelta
from urllib.parse import quote
import httpx
from pymongo import ReturnDocument
from .database import db
from .models import CompanyCandidate, SearchCriteria, now

log = logging.getLogger(__name__)


class DiscoveryProvider(ABC):
    name: str
    ttl_days = 30
    interval = 1.0
    def __init__(self):
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def get_json(self, url: str, params: dict | None = None, auth=None, headers=None):
        key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
        cache = db().provider_cache.find_one({"provider": self.name, "key": key, "expires_at": {"$gt": now()}})
        if cache:
            return cache["data"]
        async with self._lock:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0, self.interval - (loop.time() - self._last)))
            self._last = loop.time()
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                for attempt in range(3):
                    response = await client.get(url, params=params, auth=auth, headers={"User-Agent": "ProspectIQ/0.1 (source research; contact in README)", **(headers or {})})
                    db().api_usage.update_one({"provider": self.name, "date": now().date().isoformat()}, {"$inc": {"requests": 1}, "$set": {"last_status": response.status_code, "updated_at": now()}}, upsert=True)
                    if response.status_code == 429 or response.status_code >= 500:
                        try:
                            delay = int(response.headers.get("Retry-After", "0")) or 2 ** attempt
                        except ValueError:
                            delay = 2 ** attempt
                        await asyncio.sleep(min(delay, 30))
                        continue
                    response.raise_for_status()
                    data = response.json()
                    db().provider_cache.replace_one({"provider": self.name, "key": key}, {"provider": self.name, "key": key, "data": data, "expires_at": now() + timedelta(days=self.ttl_days)}, upsert=True)
                    return data
        raise RuntimeError(f"{self.name} unavailable after retries")

    @abstractmethod
    async def search(self, criteria: SearchCriteria) -> list[CompanyCandidate]: ...


class EnrichmentProvider(ABC):
    """A future licensed source can contribute only fields it can verify."""
    @abstractmethod
    async def enrich(self, company: dict) -> CompanyCandidate | None: ...


class FundingProvider(ABC):
    @abstractmethod
    async def get_funding(self, company: dict) -> dict | None: ...


class PeopleProvider(ABC):
    @abstractmethod
    async def get_people(self, company: dict) -> list[dict]: ...


class GLEIFProvider(DiscoveryProvider):
    name = "GLEIF"
    async def search(self, criteria):
        if not criteria.query.strip():
            return []
        params = {"filter[entity.legalName]": criteria.query.strip(), "page[size]": 25}
        if criteria.country_code:
            params["filter[entity.legalAddress.country]"] = criteria.country_code.upper()
        data = await self.get_json("https://api.gleif.org/api/v1/lei-records", params)
        results = []
        for item in data.get("data", []):
            entity = (item.get("attributes") or {}).get("entity") or {}
            address = entity.get("legalAddress") or {}
            name = (entity.get("legalName") or {}).get("name")
            if not name:
                continue
            date = entity.get("creationDate")
            results.append(CompanyCandidate(name=name, legal_name=name,
                location={"country_code": address.get("country"), "region": address.get("region"), "city": address.get("city"), "address": " ".join(address.get("addressLines") or []) or None},
                incorporated_year=int(date[:4]) if isinstance(date, str) and date[:4].isdigit() else None,
                company_status=entity.get("status"), external_ids={"gleif": item.get("id", "")},
                source_name=self.name, source_url=f"https://search.gleif.org/#/record/{item.get('id')}", source_type="official API"))
        return results


class CompaniesHouseProvider(DiscoveryProvider):
    name = "Companies House"
    interval = 0.6
    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key

    async def search(self, criteria):
        if not self.api_key or not criteria.query.strip() or criteria.country_code not in (None, "GB"):
            return []
        data = await self.get_json("https://api.company-information.service.gov.uk/search/companies", {"q": criteria.query.strip(), "items_per_page": 30}, auth=(self.api_key, ""))
        results = []
        for item in data.get("items", []):
            number = item.get("company_number")
            if not number:
                continue
            address = item.get("address") or {}
            date = item.get("date_of_creation")
            results.append(CompanyCandidate(name=item.get("title") or number, legal_name=item.get("title"),
                location={"country_code": "GB", "region": address.get("region"), "city": address.get("locality"), "address": item.get("address_snippet")},
                incorporated_year=int(date[:4]) if date and date[:4].isdigit() else None,
                company_status=item.get("company_status"), external_ids={"companies_house": number},
                source_name=self.name, source_url=f"https://find-and-update.company-information.service.gov.uk/company/{quote(number)}", source_type="official API"))
        return results


class WikidataProvider(DiscoveryProvider):
    name = "Wikidata"
    interval = 1.0
    ttl_days = 30

    async def search(self, criteria):
        if not criteria.query.strip():
            return []
        endpoint = "https://www.wikidata.org/w/api.php"
        found = await self.get_json(endpoint, {"action": "wbsearchentities", "search": criteria.query.strip(), "language": "en", "format": "json", "limit": 20})
        ids = [x["id"] for x in found.get("search", []) if x.get("id", "").startswith("Q")]
        if not ids:
            return []
        data = await self.get_json(endpoint, {"action": "wbgetentities", "ids": "|".join(ids), "props": "claims|descriptions|labels", "languages": "en", "format": "json"})
        linked_ids = set()
        for entity in data.get("entities", {}).values():
            for prop in ("P452", "P17", "P112", "P169"):
                for claim in (entity.get("claims") or {}).get(prop, [])[:3]:
                    value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                    if isinstance(value, dict) and value.get("id"):
                        linked_ids.add(value["id"])
        linked = {}
        if linked_ids:
            related = await self.get_json(endpoint, {"action": "wbgetentities", "ids": "|".join(sorted(linked_ids)[:50]), "props": "claims|labels", "languages": "en", "format": "json"})
            linked = related.get("entities", {})
        results = []
        for item_id, entity in data.get("entities", {}).items():
            claims = entity.get("claims") or {}
            description = ((entity.get("descriptions") or {}).get("en") or {}).get("value", "")
            if not any(word in description.casefold() for word in ("company", "startup", "business", "corporation", "firm", "enterprise")):
                continue
            def value(prop):
                try:
                    return claims[prop][0]["mainsnak"]["datavalue"]["value"]
                except (KeyError, IndexError, TypeError):
                    return None
            website = value("P856")
            founded = value("P571")
            employees = value("P1128")
            name = ((entity.get("labels") or {}).get("en") or {}).get("value")
            if not name:
                continue
            year = None
            if isinstance(founded, dict):
                try:
                    year = int(founded["time"].lstrip("+")[:4])
                except (KeyError, ValueError):
                    pass
            count = None
            if isinstance(employees, dict):
                try:
                    count = int(float(employees["amount"]))
                except (KeyError, ValueError):
                    pass
            def related_entities(prop):
                values = []
                for claim in claims.get(prop, [])[:3]:
                    linked_value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                    if isinstance(linked_value, dict) and linked_value.get("id") in linked:
                        values.append(linked[linked_value["id"]])
                return values
            industries = [e.get("labels", {}).get("en", {}).get("value") for e in related_entities("P452")]
            country_entities = related_entities("P17")
            country_name = country_entities[0].get("labels", {}).get("en", {}).get("value") if country_entities else None
            country_code = None
            if country_entities:
                try:
                    country_code = country_entities[0]["claims"]["P297"][0]["mainsnak"]["datavalue"]["value"]
                except (KeyError, IndexError, TypeError):
                    pass
            founders = [{"name": e.get("labels", {}).get("en", {}).get("value"), "role": "Founder"} for e in related_entities("P112")]
            founders = [person for person in founders if person["name"]]
            executives = [{"name": e.get("labels", {}).get("en", {}).get("value"), "role": "CEO"} for e in related_entities("P169")]
            executives = [person for person in executives if person["name"]]
            results.append(CompanyCandidate(name=name, description=description or None, website=website if isinstance(website, str) else None,
                location={"country": country_name, "country_code": country_code}, industry=[x for x in industries if x], founders=founders, executives=executives,
                founded_year=year, employees={"exact": count} if count is not None else {},
                external_ids={"wikidata": item_id}, source_name=self.name, source_url=f"https://www.wikidata.org/wiki/{item_id}", source_type="open dataset"))
        return results


def live_providers():
    from .config import settings
    return [WikidataProvider(), GLEIFProvider(), CompaniesHouseProvider(settings.companies_house_api_key)]
