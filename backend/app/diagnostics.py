import asyncio
from .config import settings
from .database import db
from .integrations import CompaniesHouseService, GitHubService, SECService


async def provider_status() -> dict[str, str]:
    try:
        db().command("ping")
        mongodb = "connected"
    except Exception:
        mongodb = "unreachable"
    companies_house, github, sec = await asyncio.gather(
        CompaniesHouseService(settings.companies_house_api_key).check(),
        GitHubService(settings.github_token).check(),
        SECService(settings.sec_user_agent).check())
    return {"mongodb": mongodb, "companies_house": companies_house, "github": github, "sec": sec}
