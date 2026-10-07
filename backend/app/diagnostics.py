import asyncio
from .config import settings
from .database import db
from .integrations import GitHubService, SECService
from .integrations.common import safe_status


async def provider_status() -> dict[str, str]:
    try:
        db().command("ping")
        mongodb = "connected"
    except Exception:
        mongodb = "unreachable"
    github, sec, gleif, wikidata = await asyncio.gather(
        GitHubService(settings.github_token).check(),
        SECService(settings.sec_user_agent).check(),
        safe_status("https://api.gleif.org/api/v1/lei-records?page%5Bsize%5D=1", headers={"User-Agent": "ScoutBase/0.1"}),
        safe_status("https://www.wikidata.org/w/api.php?action=query&meta=siteinfo&format=json", headers={"User-Agent": "ScoutBase/0.1"}))
    return {"mongodb": mongodb, "gleif": gleif, "wikidata": wikidata, "github": github, "sec": sec}
