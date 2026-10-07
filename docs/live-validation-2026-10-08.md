# Live discovery validation — 8 October 2026

The four searches below ran against the real provider adapters and the existing `prospectiq` MongoDB database. GLEIF requires a company name and made no external request for these filter-only searches. Wikidata was the discovery provider queried. GitHub enriched sourced organizations where applicable. SEC enrichment did not run; the local `SEC_USER_AGENT` lacks a declared contact address, and these candidates had no applicable SEC enrichment. Counts are actual run output.

| Search | Raw | Valid | Existing duplicates | Unique in run | Enriched | Rejected | Provider failures | Final matching records |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Germany · E-commerce · 10–100 employees | 11 | 11 | 0 | 11 | 0 | 0 | 0 | **0** |
| United Kingdom · SaaS · 10–100 employees | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| United States · E-commerce · 10–100 employees | 10 | 10 | 0 | 10 | 2 GitHub | 0 | 0 | **0** |
| Worldwide · E-commerce | 15 | 15 | 3 | 15 | 3 GitHub | 0 | 0 | **30** |

The worldwide search began with 19 matching stored records and finished with 30. Its three duplicates were already stored records that were merged or refreshed. The country searches produced sourced companies, but the employee filter correctly excluded all candidates: the four German candidates with reported counts had 336, 553, 843, or 1,359 employees; the two US candidates matching country and industry with reported counts had 545 or 22,000. Seven German and six US candidates lacked a reported employee count. The current Wikidata property search returned no UK SaaS candidates. None of these runs supplied venture funding. This is a coverage gap in the free providers, not evidence that matching private companies do not exist.

All 35 company records after these runs have source records. Eighty explicitly marked legacy records and their 68 funding rounds and 80 source records were removed after provenance inspection; the two real preexisting companies were preserved. There are no legacy flags or orphaned related records. The provider cache retained 32 real response entries. Repeating the worldwide E-commerce request returned 30 fresh MongoDB matches with a “Sufficient fresh stored matches” job and **no increase** in external request counts.

Run the checks again with `python -m app.scripts.live_validation` from `backend`. Repeated runs will have different duplicate and final counts as the source cache and MongoDB grow.
