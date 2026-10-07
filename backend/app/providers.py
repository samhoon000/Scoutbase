"""Compatibility exports for the modular source provider package."""
from .source_providers.base import DiscoveryProvider, EnrichmentProvider, FundingProvider, PeopleProvider
from .source_providers.gleif import GLEIFProvider
from .source_providers.wikidata import WikidataProvider
from .source_providers.sec import SECProvider
from .source_providers.github import GitHubProvider
from .source_providers.registry import live_providers, enrichment_providers
