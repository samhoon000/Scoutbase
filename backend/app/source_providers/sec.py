from .base import DiscoveryProvider, EnrichmentProvider
from ..models import CompanyCandidate

class SECProvider(DiscoveryProvider, EnrichmentProvider):
    """Official SEC ticker directory; a ticker alone does not establish domicile."""
    name = "SEC EDGAR"
    interval = 0.2
    ttl_days = 7
    capabilities = {"company_discovery": True, "public_listing": True, "filings": True, "funding": False, "location": True}

    async def search(self, criteria):
        from ..config import settings
        from ..integrations.sec import has_declared_contact
        if not has_declared_contact(settings.sec_user_agent) or not criteria.query.strip():
            return []
        data = await self.get_json("https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": settings.sec_user_agent, "Accept": "application/json"})
        if not isinstance(data, dict):
            return []
        term = criteria.query.strip().casefold()
        results = []
        for item in data.values():
            if not isinstance(item, dict):
                continue
            name, ticker, cik = item.get("title"), item.get("ticker"), item.get("cik_str")
            if not name or cik is None or not (term in name.casefold() or term == str(ticker).casefold()):
                continue
            results.append(CompanyCandidate(name=name, external_ids={"sec_cik": str(cik).zfill(10)},
                other_urls=[f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}"],
                source_name=self.name, source_url=f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}", source_type="official API"))
            if len(results) >= 25:
                break
        return results

    async def enrich(self, company: dict):
        from ..config import settings
        from ..integrations.sec import has_declared_contact
        cik = (company.get("external_ids") or {}).get("sec_cik")
        if not has_declared_contact(settings.sec_user_agent) or not cik or not str(cik).isdigit():
            return None
        cik = str(cik).zfill(10)
        data = await self.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers={"User-Agent": settings.sec_user_agent, "Accept": "application/json"})
        if not isinstance(data, dict) or not data.get("cik") or not data.get("name"):
            return None
        address = (data.get("addresses") or {}).get("business") or {}
        recent = ((data.get("filings") or {}).get("recent") or {})
        filings = [{"form": form, "date": date, "accession": accession}
            for form, date, accession in zip(recent.get("form") or [], recent.get("filingDate") or [], recent.get("accessionNumber") or [])][:5]
        return CompanyCandidate(name=data["name"],
            location={"city": address.get("city"), "region": address.get("stateOrCountryDescription")},
            industry=[data["sicDescription"]] if data.get("sicDescription") else [],
            external_ids={**(company.get("external_ids") or {}), "sec_cik": cik},
            filing_signals={"recent_filings": filings, "tickers": data.get("tickers") or []},
            source_name=self.name, source_url=f"https://data.sec.gov/submissions/CIK{cik}.json", source_type="official API")
