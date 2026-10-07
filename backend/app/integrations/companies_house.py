from .common import safe_status


class CompaniesHouseService:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def check(self) -> str:
        if not self.api_key:
            return "not_configured"
        return await safe_status("https://api.company-information.service.gov.uk/company/00000006",
                                 auth=(self.api_key, ""), headers={"User-Agent": "ProspectIQ/0.1"})
