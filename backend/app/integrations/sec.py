from .common import safe_status
import re


def has_declared_contact(user_agent: str) -> bool:
    return bool(re.search(r"\S+@\S+\.\S+", user_agent))


class SECService:
    def __init__(self, user_agent: str):
        self.user_agent = user_agent

    async def check(self) -> str:
        if not self.user_agent:
            return "not_configured"
        if not has_declared_contact(self.user_agent):
            return "needs_contact_user_agent"
        return await safe_status("https://data.sec.gov/submissions/CIK0000320193.json",
                                 headers={"User-Agent": self.user_agent, "Accept": "application/json"})
