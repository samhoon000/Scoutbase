import httpx


def status_from_response(response: httpx.Response) -> str:
    if response.status_code == 200:
        return "connected"
    if response.status_code == 401:
        return "unauthorized_401"
    if response.status_code == 403:
        return "forbidden_403"
    if response.status_code == 429:
        return "rate_limited"
    if response.status_code >= 500:
        return "provider_unavailable"
    return f"http_{response.status_code}"


async def safe_status(url: str, *, headers: dict | None = None, auth=None) -> str:
    """Return fixed status labels only; never echo URLs, headers, or exception text."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(url, headers=headers, auth=auth)
        return status_from_response(response)
    except (httpx.TimeoutException, httpx.NetworkError):
        return "unreachable"
    except httpx.HTTPError:
        return "request_failed"
