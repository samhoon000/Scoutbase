from .common import safe_status


class SECService:
    def __init__(self, user_agent: str):
        self.user_agent = user_agent

    async def check(self) -> str:
        if not self.user_agent:
            return "not_configured"
        return await safe_status("https://data.sec.gov/submissions/CIK0000320193.json",
                                 headers={"User-Agent": self.user_agent, "Accept": "application/json"})
