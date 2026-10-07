# ProspectIQ

ProspectIQ is an MVP for researching companies that may benefit from analytics work. It combines permitted company sources, stores field provenance, scores only supported signals, and offers search, saved lists, outreach notes, a dashboard, and CSV/XLSX export. The attached brief's emphasis on **real data and honest unknowns** governs the implementation: missing funding, employees, people, websites, or social profiles remain empty.

## Run locally

Requirements: Python 3.11+, Node 20+, npm. MongoDB Atlas supplies persistent storage. Configuration is loaded from the project root `.env`, with optional overrides in `backend/.env`. When `MONGODB_URI` is absent and `DEMO_MODE=true`, the backend falls back to an in-memory MongoDB compatible store that resets on restart. The current workspace has Atlas configured, and `backend/.env` selects `DATABASE_NAME=prospectiq` without copying credentials.

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. API docs are at `http://localhost:8000/docs`.

For a new installation, copy `.env.example` to the project root `.env`, provide a MongoDB Atlas URI, and set `DATABASE_NAME=prospectiq`. The backend creates missing collections and indexes on startup. `DEMO_MODE=true` seeds 80 synthetic records once; set it to `false` to avoid demo inserts. Secrets must stay server-side. The only frontend setting is the public `NEXT_PUBLIC_API_URL`, which defaults to `http://localhost:8000` and may be set in `frontend/.env.local`.

Initialize or inspect the database without starting the server:

```powershell
cd backend
python -c "from app.database import initialize; print(initialize())"
python -m app.scripts.seed_demo
python -m app.scripts.diagnose
```

Initialization is idempotent. It creates `companies`, `funding_rounds`, `people`, `sources`, `saved_companies`, `outreach`, `searches`, `discovery_jobs`, `provider_cache`, and `api_usage`. The 28 named index definitions are in [`backend/app/database_indexes.py`](backend/app/database_indexes.py), including identity/domain, country/industry/score, employee and funding filters, people and source lookup, user workflow, job status, cache TTL, and API usage. No existing documents are deleted or overwritten during initialization. The seed command skips when demo records already exist.

## Provider selection (checked 7 October 2026)

| Data | Provider | Free? | Free limit | API/key | Fields actually used | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Company discovery, legal identity | [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api/) | Yes | No public fixed quota found; adapter spaces requests to 1/s and obeys 429 | REST, no key | Legal name, LEI, legal location, entity creation year/status when supplied | Global LEI entities; coverage is biased toward entities with an LEI, not startups generally. Entity creation is not labeled as startup founding. [LEI data terms](https://www.gleif.org/en/meta/lei-data-terms-of-use). |
| Company discovery, business details, people | [Wikidata API](https://www.wikidata.org/wiki/Wikidata:Data_access) | Yes | Fair-use throttling; no fixed daily quota in the cited policy | MediaWiki API, no key | Name, description, website, founding year, reported headcount, country, industry, founders, CEO when statements exist | Structured data is [CC0](https://www.wikidata.org/wiki/Wikidata:Licensing). Community data may be sparse or stale. Identifiable User-Agent and conservative 1/s pacing. [Service etiquette](https://wikitech.wikimedia.org/wiki/Wikidata_Query_Service/Technical_interactions). |
| UK company discovery | [Companies House](https://developer.company-information.service.gov.uk/get-started) | Yes | [600 requests / 5 minutes](https://developer.company-information.service.gov.uk/developer-guidelines/) | REST; `COMPANIES_HOUSE_API_KEY` required | Registered name, number, address, incorporation year, status | GB only. Incorporation is kept separate from founding. API key sent by HTTP Basic auth. [Authentication](https://developer.company-information.service.gov.uk/authentication). |
| Private startup funding, rounds, investors | None selected | — | — | — | `null` / empty | No verified, commercially usable, general global free API for these fields was established. Do not infer funding from press mentions. Add a licensed adapter later. |
| Website/domain/social links | Wikidata | Yes | Same as above | Same as above | Official website when stated | Domain is normalized from the website. Social profiles are not synthesized. Automated crawling of company sites is deliberately not enabled. |
| Public professional profiles | Wikidata | Yes | Same as above | Same as above | Founder/CEO names when stated | No LinkedIn scraping, email guessing, or people enrichment from restricted sites. |

Additional sources evaluated: [Product Hunt API](https://api.producthunt.com/v2/docs) says commercial use requires permission, so it is **excluded**. [OpenCorporates API](https://api.opencorporates.com/documentation/API-Reference) has free access tied to open data/share-alike conditions, so it is **excluded** from this closed/commercially oriented MVP unless licensing is reviewed. [SEC data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) are free but cover SEC filers and XBRL disclosures, not general private startup funding; they are not presented as a funding provider. Its [fair-access rate](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits) is 10 requests/s if added later.

GLEIF and Wikidata structured data are CC0. Companies House register information is supplied under its statutory public-register framework; confirm any applicable reuse conditions for the particular output before commercial launch. ProspectIQ displays source links for each company and retains the source name, URL, fields, collection time, and confidence. Free terms and quotas can change.

## How discovery works

`POST /api/companies/discover` returns a job ID. The frontend polls `GET /api/jobs/{id}`. The job queries Wikidata, GLEIF, and Companies House independently, normalizes names/domains, matches an existing entity by domain, external ID, or normalized name plus country, merges only previously missing fields, stores source records, calculates an explainable score, and indexes the result. A provider failure is recorded on the job without aborting other providers. Live discovery currently requires a company name/keyword; broad industry-only worldwide discovery is **not supported** by the selected free APIs.

Provider HTTP responses are cached in MongoDB with a 30-day TTL. Calls use per-provider pacing, retry with backoff for 429/5xx, and write request counts/status to `api_usage`. Company records are reused on identity match. There is no fake enrichment: a refresh via discovery may fill missing fields, while fields with no source remain empty. Periodic scheduling is not automated yet.

The in-process `BackgroundTasks` runner is an MVP job abstraction. Jobs persist in MongoDB but an active job can be interrupted by a server restart; a durable queue such as Celery/Redis is needed for multi-instance production operation.

## Scoring

The six configurable factors in `backend/app/scoring.py` total 100 points: funding 20, recent growth 20, data intensity 20, industry relevance 15, company size 15, analytics opportunity 10. Missing facts contribute **zero** rather than a guessed positive score. Explanations cite the observed signals, and suggested projects are labeled as opportunities, not verified company needs. Source confidence is evidence coverage, not a probability that the company will buy services.

## Demo and API

Demo mode generates 80 **fictional** records across 10 countries and 11 industries. Every record has `demo` and `is_demo` flags and a demo source; the UI displays `DEMO DATA`. Search, filters, sorting, pagination, detail pages, saving, outreach, dashboard, and export work without external provider credentials. Demo funding values, stages, and rounds are synthetic only.

Key endpoints: `/api/health`, `/api/health/providers`, `/api/companies`, `/api/companies/search`, `/api/companies/{id}`, `/api/companies/discover`, `/api/jobs/{id}`, `/api/saved-companies`, `/api/outreach`, `/api/searches`, `/api/dashboard`, `/api/export?format=csv|xlsx`. The provider health endpoint returns only fixed status labels; it never returns credentials. GitHub and SEC currently have separate server-side connectivity services, but they are not used as startup funding sources. OpenAPI documentation covers request and response shapes. Exports accept comma-separated IDs and cap at 10,000 records.

## Tests and limitations

```powershell
cd backend
python -m pytest -q
python -m app.scripts.verify_workflow
python -m app.scripts.diagnose
$env:PYTHONPATH='.'; python scripts/check_providers.py
cd ../frontend
npm run build
```

The app has no real user authentication; workflow records use one local development identity. Do not expose the API publicly until authentication, user isolation, request rate limiting, and a durable worker are implemented. Atlas connection, initialization, seeding, and the temporary-user workflow were verified in this workspace. Companies House currently returns HTTP 401 with the locally configured key and must be corrected before that adapter can provide live data. GitHub and SEC connectivity checks passed. The no-key provider smoke check verifies endpoint access, not long-term data coverage. Private startup funding, employee counts, and founders remain sparse with these free sources. The `POST /api/companies/{id}/enrich` endpoint currently explains how to refresh via discovery; it is not an independent enrichment job.
