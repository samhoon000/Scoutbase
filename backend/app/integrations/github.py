from .common import safe_status


class GitHubService:
    def __init__(self, token: str):
        self.token = token

    async def check(self) -> str:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "ScoutBase/0.1"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return await safe_status("https://api.github.com/orgs/github", headers=headers)
