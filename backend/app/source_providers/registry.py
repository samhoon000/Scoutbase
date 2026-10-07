from .gleif import GLEIFProvider
from .wikidata import WikidataProvider
from .sec import SECProvider
from .github import GitHubProvider


def live_providers():
    return [GLEIFProvider(), WikidataProvider()]


def enrichment_providers():
    return [SECProvider(), GitHubProvider()]
