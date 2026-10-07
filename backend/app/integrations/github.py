from .common import safe_status


class GitHubService:
    def __init__(self, token: str):
        self.token = token

    async def check(self) -> str:
        if not self.token:
            return "not_configured"
        return await safe_status("https://api.github.com/user", headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "User-Agent": "ProspectIQ/0.1"})
