# ScoutBase

Find the companies that need you. ScoutBase is a live-data-only company intelligence and prospect research workspace. It discovers real entities from permitted free sources, combines sourced facts in MongoDB, and infers potential analytics opportunities from verified characteristics. Missing funding, employees, founders, emails, and profiles remain unknown. Current sources do not provide complete global private-company coverage.

## Run locally

Use Python 3.11+, Node 20+, npm, and MongoDB Atlas. Copy the root .env.example to .env. Keep DATABASE_NAME=prospectiq to avoid a database migration. Never put credentials in NEXT_PUBLIC_*.

    cd backend
    python -m pip install -r requirements.txt
    python -m uvicorn app.main:app --reload --port 8000

In another terminal:

    cd frontend
    npm install
    npm run dev

Open http://localhost:3000 and API docs at http://localhost:8000/docs. `MONGODB_URI` is required. An empty `prospectiq` database is supported; the first filter search queries MongoDB and then starts applicable real providers. No company records are seeded. If a provider cannot supply a requested field, that field remains unknown and positive filters do not match it.

## Free source comparison

| Data | Provider | Free? | Limit / access | Fields and fallback |
| --- | --- | --- | --- | --- |
| Global legal entities | [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api/) | Yes | No key; no fixed public quota found; paced at 1 request/s | Legal name, LEI, registered address, entity creation year/status. Wikidata is the discovery fallback. |
| Company details and people | [Wikidata Action API](https://www.wikidata.org/wiki/Wikidata:Data_access) | Yes | No key; [Wikimedia limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits) apply; paced at 1 request/s | Description, website, industry, country, founding year, reported employees, founders/CEO, sourced social IDs. GLEIF fills legal identity gaps. |
| SEC filers and filings | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Yes | SEC_USER_AGENT with a real contact address required; [10 requests/s](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits) maximum | Sourced CIK, filings, SIC description, ticker, business address. The ticker directory returns HTTP 403 here, so default discovery omits it; data.sec.gov enrichment activates when a CIK and compliant User-Agent are available. |
| Public developer presence | [GitHub REST API](https://docs.github.com/en/rest/orgs/orgs) | Yes | Optional GITHUB_TOKEN; [rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) apply | A sourced organization URL can provide description, website, public repo count, and update time. |
| Private startup funding, rounds, investors | No approved general source | — | — | Remain null or empty unless a real source supplies them. |

See [data sources](docs/data-sources.md) for terms, quotas, fields, attribution, and alternatives. See [discovery architecture](docs/discovery-architecture.md) for merge rules.

## Discovery and workflow

Discover is the primary workflow. Choose structured country, industry, company type, size, funding, growth, analytics opportunity, and prospect quality filters, then select **Find Companies**. Results and counts come from the MongoDB query, with AND across filter groups and OR within country, industry, or company type selections. Industry aliases such as `ecommerce` and `E-commerce` are normalized for matching. The same page supports sorting, pagination, company saving, and a source-aware explanation of each match. Clear all reruns an unfiltered search. On small screens the filters open in a sheet.

Saved searches persist the full criteria object, including ranges, multi-select fields, sort, and order. **Run** restores the criteria in Discover and queries current company data; rename and delete are available in Searches.

The country picker offers ISO two-letter country choices; common industry categories remain selectable even before the database has any companies. Company type, region, city, and funding stage choices reflect sourced records. Growth signals that require verified history or activity data stay disabled when no records carry that evidence. The analytics opportunity score is an industry-based estimate, shown as such. Missing values never satisfy a positive filter. External discovery currently supports one country, one industry, or a company name per run; multi-country and multi-industry filters search stored sourced records. Size, funding, growth, and opportunity filters narrow only the records for which real providers supplied those fields.

POST /api/companies/discover accepts a name, industry, or ISO country code and returns a job ID. GET /api/jobs/{id} reports actual raw, unique, new, and enriched counts and provider status. Name discovery uses GLEIF and Wikidata. Country or industry discovery uses bounded Wikidata property search. SEC and GitHub enrich only companies with sourced identifiers or URLs. A provider failure does not abort the other sources.

MongoDB is searched first and kept as the growing intelligence database. A fresh full page of matching records avoids another provider call; a completed identical discovery job is reused for REFRESH_DAYS unless force_refresh=true. Raw responses are cached in provider_cache. Requests, successes, failures, rate limits, and cache hits are tracked in api_usage. The company profile exposes field sources and conflicts. Prospect scores and suggested projects are inferred intelligence, separate from sourced facts.

Search, pagination, filters, profiles, saved companies, outreach notes, search history, dashboard, and CSV/XLSX export are available. Outreach records do not send emails. The four requested live coverage checks can be repeated with `python -m app.scripts.live_validation` from `backend`; each prints real provider counts and the final MongoDB match count. See the [live validation report](docs/live-validation-2026-10-08.md) for observed gaps.

## Verify

    cd backend
    python -m pytest -q
    python -m app.scripts.verify_workflow
    python -m app.scripts.diagnose
    cd ../frontend
    npm run build

This local MVP uses one development user, in-process jobs, and no public API authentication or request rate limiter. Do not expose it publicly until these controls and a durable worker are implemented. Public source coverage is sparse for private startup funding and headcount. The website crawler is disabled; third-party pages are not scraped simply because they are public.

For SEC enrichment, set SEC_USER_AGENT to your organization name followed by a real contact email address, following the [SEC's declared User-Agent example](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data). The current local value lacks that contact address, so ScoutBase reports needs_contact_user_agent and skips SEC calls until it is corrected. Do not paste the address into frontend configuration.
