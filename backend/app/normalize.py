import re
from urllib.parse import urlparse


SUFFIXES = re.compile(r"\b(incorporated|corporation|company|limited|technologies|technology|private|pvt|inc|corp|ltd|llc|gmbh|ag|plc)\b", re.I)


def normalized_name(value: str) -> str:
    value = re.sub(r"[^\w\s]", " ", value.casefold())
    value = SUFFIXES.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def domain_from_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value if "://" in value else "https://" + value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.lower().removeprefix("www.")
    if host in {"localhost"} or host.endswith(".local") or "." not in host:
        return None
    return host


def safe_public_url(value: str | None) -> str | None:
    if not value or not domain_from_url(value):
        return None
    parsed = urlparse(value if "://" in value else "https://" + value)
    return parsed.geturl()


def source_record(candidate, fields: list[str]) -> dict:
    return {"source_name": candidate.source_name, "source_url": candidate.source_url,
            "source_type": candidate.source_type, "fields_provided": fields,
            "collected_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "confidence": 1.0 if candidate.source_type == "official API" else 0.7}
