# ScoutBase data sources

Reviewed 8 October 2026. Check linked provider terms and quotas before a public launch. The adapters make no assumption that a public webpage permits automated scraping. ScoutBase uses only live sourced company records; these providers do not offer complete global private-company coverage.

| Data | Provider | Free? | Free limit / authentication | Supplied fields | Fallback |
| --- | --- | --- | --- | --- | --- |
| Global legal company discovery | [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api/) | Yes | No key; no fixed public daily quota identified; 1 request/s local pacing | LEI, legal name, registered location, entity creation date, status | Wikidata |
| Company discovery and details | [Wikidata Action API](https://www.wikidata.org/wiki/Wikidata:Data_access) | Yes | No key; [Wikimedia rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits) and 429 apply; 1 request/s local pacing | Name, description, website, country, industry, founding year, reported headcount, founders, CEO, LinkedIn company ID, GitHub account, SEC CIK | GLEIF for legal identity; SEC/GitHub for fields they verify |
| SEC filers | [SEC submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Yes | SEC_USER_AGENT with contact email required; [fair access](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits) capped at 10 requests/s; adapter paces at 5/s | Official CIK identity, SIC description, tickers, business address, recent filing dates/forms | Wikidata for nonfilers; unknown when unavailable |
| GitHub organizations | [GitHub REST orgs](https://docs.github.com/en/rest/orgs/orgs) | Yes | GITHUB_TOKEN optional; [primary and secondary limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api); 1 request/s local pacing | Public org description, site, public repo count, update time | Unknown when no sourced URL |
| Private funding, rounds, investors | None selected | — | No general commercial-use free API verified | Null / empty | Optional future licensed adapter |

## Licenses, attribution, and access

- GLEIF provides LEI data under its [data terms](https://www.gleif.org/en/meta/lei-data-terms-of-use/). The structured public LEI data is free/CC0. Coverage means organizations with LEIs; it is not a complete startup directory. ScoutBase keeps the LEI and record URL. Creation date is stored as incorporation/entity creation, never silently as startup founding.
- Wikidata structured data is [CC0](https://www.wikidata.org/wiki/Wikidata:Licensing). Attribution is not legally required for CC0 but ScoutBase links to each item and records retrieval time. Community statements may be stale or incomplete. The app uses the Action API, including [documented property search](https://www.mediawiki.org/wiki/Help:Extension:WikibaseCirrusSearch), rather than bulk scraping. Country/industry queries are bounded to 25 IDs per run.
- SEC public submissions require a declared SEC_USER_AGENT with an organization name and real contact email, as illustrated in the [SEC access instructions](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), plus conservative request pacing. The app links the exact submissions endpoint and does not treat filings or securities offerings as venture funding. The official ticker-directory URL at www.sec.gov/files/company_tickers.json returned HTTP 403 in this environment; the adapter exists but is omitted from default discovery. data.sec.gov returned HTTP 200 in a smoke check. The current local User-Agent lacks a contact address, so SEC health reports needs_contact_user_agent and SEC enrichment skips requests until corrected. SEC data is restricted to filers, not global startups.
- GitHub REST permits public org metadata under its [API terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service). Unauthenticated primary quota is typically 60 requests/hour; authenticated quota is generally 5,000/hour, with secondary limits also applying. The app only calls /orgs/{handle} when the handle came from a sourced URL. It does not guess organization accounts or use public repository count as a verified growth metric. Source links are displayed.
- Company websites are not crawled in this MVP. A website URL can be stored when a permitted structured source provides it.
- LinkedIn URLs are taken only from Wikidata's [P4264 company ID](https://www.wikidata.org/wiki/Property:P4264). ScoutBase does not scrape LinkedIn or synthesize profile URLs.
- GitHub account identifiers use Wikidata [P2037](https://www.wikidata.org/wiki/Property:P2037); SEC CIK uses [P5531](https://www.wikidata.org/wiki/Property:P5531); GLEIF LEI cross-links use [P1278](https://www.wikidata.org/wiki/Property:P1278).

## Investigated but not enabled

| Provider | Current finding | Decision |
| --- | --- | --- |
| [OpenCorporates API](https://api.opencorporates.com/documentation/API-Reference) | Free API access is intended for qualifying open/share-alike projects and requires an API account/key; [self-service terms](https://opencorporates.com/legal-information/self-service-api-terms-of-service/) and [license](https://opencorporates.com/legal/licence/) require review for this commercial-oriented product. | No active adapter or key requirement. Add only after appropriate permission/license. |
| [Product Hunt API](https://api.producthunt.com/v2/docs) | Commercial use requires permission. | Excluded. |
| Search engine free tiers | Quotas, reuse rights, and downstream company-data rights vary by provider. | No general crawler/search provider enabled. |
| Company websites / professional networks | Public visibility alone does not authorize automated extraction. | No scraping. |

No paid provider is needed for the app to run. Funding, employee counts, founders, investors, emails, and social profiles stay unknown whenever selected sources do not provide them. Source records include provider, URL, fields, timestamp, and reliability. Provider responses are cached with TTL; usage is counted per provider/day. Rate-limit responses stop the current provider attempt and leave the job partially successful.
