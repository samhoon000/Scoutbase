import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from datetime import timedelta, timezone
import httpx
from ..database import db
from ..models import CompanyCandidate, SearchCriteria, now

class DiscoveryProvider(ABC):
    name: str
    capabilities: dict[str, bool] = {"company_discovery": True}
    ttl_days = 30
    interval = 1.0
    def __init__(self):
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def get_json(self, url: str, params: dict | None = None, auth=None, headers=None):
        key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
        cache = db().provider_cache.find_one({"provider": self.name, "key": key, "expires_at": {"$gt": now()}})
        if cache:
            db().api_usage.update_one({"provider": self.name, "date": now().date().isoformat()}, {"$inc": {"cache_hits": 1}}, upsert=True)
            return cache.get("response", cache.get("data"))
        async with self._lock:
            cache = db().provider_cache.find_one({"provider": self.name, "key": key, "expires_at": {"$gt": now()}})
            if cache:
                db().api_usage.update_one({"provider": self.name, "date": now().date().isoformat()}, {"$inc": {"cache_hits": 1}}, upsert=True)
                return cache.get("response", cache.get("data"))
            usage = db().api_usage.find_one({"provider": self.name, "date": now().date().isoformat()}) or {}
            blocked_until = usage.get("blocked_until")
            if blocked_until and blocked_until.replace(tzinfo=blocked_until.tzinfo or timezone.utc) > now():
                raise RuntimeError(f"{self.name} rate limited")
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0, self.interval - (loop.time() - self._last)))
            self._last = loop.time()
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                for attempt in range(3):
                    try:
                        response = await client.get(url, params=params, auth=auth, headers={"User-Agent": "ScoutBase/0.1 (research tool; contact in README)", **(headers or {})})
                    except (httpx.TimeoutException, httpx.TransportError):
                        db().api_usage.update_one({"provider": self.name, "date": now().date().isoformat()}, {"$inc": {"requests": 1, "failures": 1}, "$set": {"updated_at": now()}}, upsert=True)
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2 ** attempt)
                        continue
                    counters = {"requests": 1, "rate_limits": int(response.status_code == 429), "successes": int(response.is_success), "failures": int(not response.is_success and response.status_code != 429)}
                    db().api_usage.update_one({"provider": self.name, "date": now().date().isoformat()}, {"$inc": counters, "$set": {"last_status": response.status_code, "updated_at": now()}}, upsert=True)
                    if response.status_code == 429:
                        try:
                            retry_seconds = max(60, min(int(response.headers.get("Retry-After", "60")), 3600))
                        except ValueError:
                            retry_seconds = 60
                        db().api_usage.update_one({"provider": self.name, "date": now().date().isoformat()},
                            {"$set": {"blocked_until": now() + timedelta(seconds=retry_seconds)}}, upsert=True)
                        raise RuntimeError(f"{self.name} rate limited")
                    if response.status_code >= 500:
                        try:
                            delay = int(response.headers.get("Retry-After", "0")) or 2 ** attempt
                        except ValueError:
                            delay = 2 ** attempt
                        if attempt < 2:
                            await asyncio.sleep(min(delay, 30))
                        continue
                    response.raise_for_status()
                    try:
                        data = response.json()
                    except ValueError:
                        db().api_usage.update_one({"provider": self.name, "date": now().date().isoformat()}, {"$inc": {"malformed_responses": 1}}, upsert=True)
                        raise
                    db().provider_cache.replace_one({"provider": self.name, "key": key}, {"provider": self.name, "key": key, "request_hash": key, "response": data, "created_at": now(), "expires_at": now() + timedelta(days=self.ttl_days)}, upsert=True)
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
