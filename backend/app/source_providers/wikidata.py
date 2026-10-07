from .base import DiscoveryProvider
from ..models import CompanyCandidate

class WikidataProvider(DiscoveryProvider):
    name = "Wikidata"
    capabilities = {"company_discovery": True, "website": True, "industry": True, "people": True, "employees": True, "location": True}
    interval = 1.0
    ttl_days = 30

    async def search(self, criteria):
        endpoint = "https://www.wikidata.org/w/api.php"
        if criteria.query.strip():
            found = await self.get_json(endpoint, {"action": "wbsearchentities", "search": criteria.query.strip(), "language": "en", "format": "json", "limit": 20})
            ids = [x["id"] for x in found.get("search", []) if x.get("id", "").startswith("Q")]
        elif criteria.industry or criteria.country_code:
            industry_id = None
            if criteria.industry:
                found = await self.get_json(endpoint, {"action": "wbsearchentities", "search": criteria.industry[:80], "language": "en", "format": "json", "limit": 10})
                industry_id = next((x["id"] for x in found.get("search", [])
                    if x.get("id", "").startswith("Q") and x.get("label", "").casefold() == criteria.industry.casefold()), None)
                if not industry_id:
                    return []
            search_terms = [f"haswbstatement:P452={industry_id}" if industry_id else "haswbstatement:P31=Q783794"]
            if criteria.country_code:
                country = criteria.country_code.upper()
                if len(country) != 2 or not country.isalpha():
                    return []
                country_result = await self.get_json(endpoint, {"action": "query", "list": "search", "srsearch": f"haswbstatement:P297={country}", "srnamespace": 0, "srlimit": 5, "format": "json"})
                country_id = next((x.get("title") for x in country_result.get("query", {}).get("search", []) if x.get("title", "").startswith("Q")), None)
                if not country_id:
                    return []
                search_terms.append(f"haswbstatement:P17={country_id}")
            matches = await self.get_json(endpoint, {"action": "query", "list": "search", "srsearch": " ".join(search_terms), "srnamespace": 0, "srlimit": 25, "format": "json"})
            ids = [x["title"] for x in matches.get("query", {}).get("search", []) if x.get("title", "").startswith("Q")]
        else:
            return []
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
            if not any(word in description.casefold() for word in ("company", "startup", "business", "corporation", "firm", "enterprise", "manufacturer", "bank", "retailer")):
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
            if criteria.country_code and country_code != criteria.country_code.upper():
                continue
            github_handle = value("P2037")
            linkedin_id = value("P4264")
            sec_cik = value("P5531")
            lei = value("P1278")
            public_urls = [f"https://github.com/{github_handle}"] if isinstance(github_handle, str) and github_handle else []
            linkedin_url = f"https://www.linkedin.com/company/{linkedin_id}/" if isinstance(linkedin_id, str) and linkedin_id else None
            external_ids = {"wikidata": item_id}
            if isinstance(sec_cik, str) and sec_cik.isdigit():
                external_ids["sec_cik"] = sec_cik.zfill(10)
            if isinstance(lei, str) and len(lei) == 20 and lei.isalnum():
                external_ids["gleif"] = lei.upper()
            founders = [{"name": e.get("labels", {}).get("en", {}).get("value"), "role": "Founder"} for e in related_entities("P112")]
            founders = [person for person in founders if person["name"]]
            executives = [{"name": e.get("labels", {}).get("en", {}).get("value"), "role": "CEO"} for e in related_entities("P169")]
            executives = [person for person in executives if person["name"]]
            results.append(CompanyCandidate(name=name, description=description or None, website=website if isinstance(website, str) else None,
                linkedin_url=linkedin_url, other_urls=public_urls,
                location={"country": country_name, "country_code": country_code}, industry=[x for x in industries if x], founders=founders, executives=executives,
                founded_year=year, employees={"exact": count} if count is not None else {},
                external_ids=external_ids, source_name=self.name, source_url=f"https://www.wikidata.org/wiki/{item_id}", source_type="open dataset"))
        return results
