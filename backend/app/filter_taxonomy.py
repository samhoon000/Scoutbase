"""Search vocabulary. Labels are taxonomy, not claims about company records."""

ALIASES = {
    "e-commerce": {"e-commerce", "ecommerce", "online retail"},
    "saas": {"saas", "software as a service"},
    "fintech": {"fintech", "financial technology"},
    "healthcare": {"healthcare", "health tech", "healthtech"},
    "edtech": {"edtech", "education technology"},
    "d2c": {"d2c", "direct to consumer", "direct-to-consumer"},
}


def industry_aliases(value: str) -> set[str]:
    term = value.strip().casefold()
    for names in ALIASES.values():
        if term in names:
            return names
    return {term}
