"""Optional smoke check for the no-key providers: python scripts/check_providers.py"""
import asyncio
from app.models import SearchCriteria
from app.providers import GLEIFProvider, WikidataProvider


async def main():
    for provider in (GLEIFProvider(), WikidataProvider()):
        try:
            companies = await provider.search(SearchCriteria(query="Stripe"))
            print(provider.name, len(companies), [c.name for c in companies[:3]])
        except Exception as error:
            print(provider.name, type(error).__name__, str(error)[:160])


if __name__ == "__main__":
    asyncio.run(main())
