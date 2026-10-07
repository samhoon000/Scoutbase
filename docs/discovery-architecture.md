# Discovery architecture

## Flow

1. Search the real company records in MongoDB first. An empty database is valid and starts with zero results.
2. Reuse a completed identical discovery job for REFRESH_DAYS unless force_refresh=true. If at least one requested page of matching records is fresh, return the stored matches without a provider call.
3. Run applicable discovery adapters independently. GLEIF requires a company name and is skipped for industry-only searches. Wikidata supports bounded name, country, or industry search. SEC ticker discovery is implemented but disabled in the default registry because its official directory returned HTTP 403 here.
4. Resolve identities using domain, external identifier, sourced LinkedIn URL, then an exact normalized name with country and city when unique. A unique same-name/country match can also merge when one record has a sourced website and domains do not conflict. Ambiguous matches are stored as possible_matches for review.
5. Merge fields. Missing values are filled; a higher-confidence source can supersede a lower-confidence value. A same-quality source can refresh a value whose prior evidence is older than REFRESH_DAYS. Disagreement is retained in field_conflicts. Sources and field_evidence include provider, URL, time, and confidence.
6. Enrich matched companies through SEC when a CIK exists and through GitHub when a public organization URL exists. A provider failure adds a status and does not abort other work.
7. Calculate a six-factor, 100-point prospect score and a separate data confidence value. Prospect scores and project ideas are inferred; company facts are sourced.
8. Persist companies, sources, people, funding rounds, discovery jobs, response cache, and daily API usage in the existing prospectiq MongoDB database.

Provider modules live under backend/app/source_providers. The registry determines active adapters and can be extended without changing the route. Discovery jobs report actual raw, valid, duplicate, unique, enriched, and rejected candidates, missing fields, provider status, and errors. The API returns paginated MongoDB results; it never sends the whole collection to the browser. Free providers have limited private-company coverage; a filtered search may correctly return zero.

## Caching and quotas

The shared HTTP client hashes URL and parameters and checks provider_cache before an external call. Cache records store provider, request_hash, response, created_at, and expires_at. Successful responses have a 30-day default TTL; SEC and GitHub use 7 days. Calls are paced per adapter. Timeouts and server errors retry with exponential backoff. HTTP 429 stops that provider immediately; it is not bypassed. api_usage records requests, successes, failures, rate limits, and cache hits by day.

## Data boundaries

Funding remains unknown unless a permitted source actually supplies a funding event. SEC filings are not venture funding. GitHub repositories are activity signals, not evidence of team size or growth. Creation/incorporation dates are distinct from founding dates. Industry-based scores and potential projects are labeled as inferences, not reported facts.

## Operating limits

The current background task runs in the FastAPI process. A process restart can interrupt a job; multi-instance deployment needs a durable queue. The local MVP uses a single development user. Add authentication, user isolation, and API request rate limiting before exposing it publicly. Source-specific quotas and licenses need periodic review.
