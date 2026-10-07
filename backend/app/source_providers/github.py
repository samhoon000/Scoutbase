from urllib.parse import quote
from .base import DiscoveryProvider, EnrichmentProvider
from ..models import CompanyCandidate

class GitHubProvider(EnrichmentProvider, DiscoveryProvider):
    """Public organization metadata for an explicitly sourced organization URL."""
    name = "GitHub"
    interval = 1.0
    ttl_days = 7
    capabilities = {"company_discovery": False, "technology_signals": True, "website": True, "description": True}

    async def search(self, criteria):
        return []

    async def enrich(self, company: dict):
        from ..config import settings
        from urllib.parse import urlparse
        handle = None
        for url in company.get("other_urls") or []:
            parsed = urlparse(url)
            if parsed.hostname in ("github.com", "www.github.com"):
                path = parsed.path.strip("/").split("/")
                if len(path) == 1 and path[0] and path[0] not in {"topics", "orgs", "users"}:
                    handle = path[0]
                    break
        if not handle:
            return None
        headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        data = await self.get_json(f"https://api.github.com/orgs/{quote(handle)}", headers=headers)
        if not isinstance(data, dict) or not data.get("id"):
            return None
        website = data.get("blog")
        return CompanyCandidate(name=company["name"], description=data.get("description") or None,
            website=website if isinstance(website, str) and website else None,
            location=company.get("location") or {},
            external_ids={**(company.get("external_ids") or {}), "github_org": str(data["id"])}, other_urls=[data.get("html_url") or f"https://github.com/{handle}"],
            technology_signals={"public_repos": data.get("public_repos"), "github_updated_at": data.get("updated_at")},
            source_name=self.name, source_url=data.get("html_url") or f"https://github.com/{handle}", source_type="public API")
