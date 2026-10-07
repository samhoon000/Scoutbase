from .base import DiscoveryProvider
from ..models import CompanyCandidate

class GLEIFProvider(DiscoveryProvider):
    name = "GLEIF"
    requires_name = True
    capabilities = {"company_discovery": True, "location": True, "legal_identity": True, "funding": False}
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
