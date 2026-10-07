# Source discovery and collection

## Development scope

Use [DEVELOPMENT_EXAMPLES.md](DEVELOPMENT_EXAMPLES.md) for the user-named employers and supplementary categories. These are isolated development fixtures/live-check targets only. Source coverage must be established on the actual sites; initial ATS adapters alone do not prove support for the selected employers. No company seed is applied to production.

## Coverage contract

A company may have many sources. Retain the monitoring request even when no usable source exists. Automatic discovery is best-effort, with evidence and correction in the portal. All-jobs means all successfully collected listings; completeness is qualified per source/run.

Brave Search API is the chosen name/discovery provider, configured by a deployment secret. Full company-name and no-careers-page discovery requires that key. Without it, URL-based monitoring remains available and the UI clearly marks automatic web discovery unavailable. Search sends company names/domains, never the CV or profile. [Official API](https://api-dashboard.search.brave.com/app/documentation/web-search/codes).

## Discovery algorithm

1. If supplied, validate the company website and fetch its homepage. Otherwise search the company name plus careers/jobs; ambiguous entities need the owner to choose.
2. Inspect same-site careers/jobs links and public recruitment-platform links. Accept a source automatically only when official-site linkage or verified employer identity supports it. Store evidence.
3. Detect Greenhouse, Lever, or Ashby boards and verify a real response, distinguishing a valid empty board from an invalid identifier.
4. For custom pages, inspect JobPosting JSON-LD, links, and rendered content. Maintain a small declarative source configuration for listing selectors/pagination where needed; no model-generated executable scraper code.
5. When no careers page is available, run company-targeted public search on the monitoring interval. Fetch candidate listing pages and verify employer identity and job evidence. Store unverified snippets as discovery candidates, never as confirmed jobs.
6. Retry unresolved discovery daily and rediscover sources weekly or after repeated failures. Never silently replace a known company with a similarly named employer.

Limit discovery to three search queries and 20 fetched candidate pages per company/run, depth two, and a deployment-wide default of 300 search calls/day. Exceeding a budget defers remaining work with visible partial coverage. Do not use freshness filtering as the only search, since older active posts could be missed. Do not infer closure from search absence.

## Initial adapters

| Adapter | Mechanism |
| --- | --- |
| Greenhouse | Public board API, listing details included/fetched as needed; preserve board and job IDs. [Documentation](https://docs.greenhouse.io/job-board.html). |
| Lever | Public postings API with global/EU endpoint handling and full pagination. [Documentation](https://github.com/lever/postings-api). |
| Ashby | Public job-board posting endpoint with compensation requested when available. [Documentation](https://developers.ashbyhq.com/docs/public-job-posting-api). |
| Generic HTTP | JobPosting JSON-LD first, then parsed listing/detail links and bounded AI extraction from visible text. |
| Generic browser | Playwright rendering through the same extraction contract for JavaScript pages; bounded pagination/load-more interactions from explicit source configuration. |
| Search discovery | Brave candidate search plus verified detail-page extraction; always non-exhaustive coverage. |

Workday and other custom platforms are not promised as dedicated adapters in v1. Their public pages may work through generic collection; otherwise show unsupported/needs configuration. Logged-in job boards, CAPTCHA bypass, private recruitment APIs, and automatic application submission are outside v1.

## Fetch contract and limits

Adapters request documents from a separate fetcher service and return normalized postings with evidence, coverage state, and next-page information. Fetcher implements HTTPX and Playwright; it has no database credentials, CV volume, inference secrets, or Docker socket. Worker performs deterministic parsing and queues any required job_extraction LLM work through the AI worker using returned text. The fetcher never receives the OpenRouter key or candidate profile.

Defaults: two HTTP requests concurrently per origin, at least two seconds between starts, four origins globally, one browser context, 30-second request/navigation timeout, 10 MiB decompressed document cap, five redirects, and 200 pages per source check. Honor published access policies and Retry-After, use a descriptive user agent, and avoid login/captcha workarounds. Hitting a cap marks the run partial and resumes in another bounded operation; never claim a complete inventory. Persist continuation cursors and accumulated observations under one inventory epoch. Reconcile omissions only after that whole traversal completes. Expire unfinished epochs after 24 hours and restart without applying missing-job closure; unstable pagination remains partial.

Use conditional requests when supported; a valid 304 preserves the last successful snapshot. On complete authoritative inventory responses, reconcile missing source associations. On errors, parsing anomalies, incomplete pagination, or budget exhaustion, preserve existing listings and mark the run incomplete. A sudden empty result from an unstructured parser is suspicious; require explicit no-vacancies evidence rather than closing the inventory.

## Network isolation

All arbitrary-page HTTP and browser requests pass through Squid. The fetcher joins internal fetch and fetch-control networks, can reach the proxy, and has no direct internet or core-services network. The control network permits worker-initiated calls to the fetcher API and return traffic only; it is not a route back into application services. Proxy joins the fetch and outbound networks, has no core-service access, permits HTTP/HTTPS on 80/443 only, and rejects non-global destinations for IPv4 and IPv6 including LAN, loopback, link-local, metadata, multicast, and tailnet ranges. [Squid ACL reference](https://www.squid-cache.org/Doc/config/acl/).

Validate scheme, credentials-in-URL, hostname, resolved destinations, and every redirect; enforce destination restrictions at actual connection time to prevent DNS rebinding. Browser subresources, WebSocket requests, and redirects must use the same egress restrictions; disable unsupported bypass transports and downloads. Application-only URL validation is insufficient. Include container-level bypass, redirect, and rebinding tests before enabling arbitrary website input. Document approved internal ntfy traffic and fixed OpenRouter API access separately; scraped URLs cannot select those destinations or receive their credentials.

AI only receives bounded extracted text and source references. Strip executable content; render job descriptions as plain text/structured sections initially. Preserve an external original-source link. Never interpret instructions found in a job page as app commands.

## Implementation checkpoint

`backend/app/collection/ats.py` implements deterministic request construction and JSON decoding for the three initial ATS providers; `contracts.py` defines normalized postings and explicit page completeness/continuation. These modules do not fetch or persist. Missing/malformed records, duplicate identities and inconsistent inventory metadata retain incomplete status; partial data cannot justify closures. Documentation contracts were rechecked against the provider links above on 2026-10-07. Durable epochs and scheduling now have PostgreSQL-backed tests. Isolated fetching, the portal/API integration and live employer coverage remain to be implemented and validated.

The scheduler emits one durable page operation at a time on the fetch queue. Each continuation shares a persisted run/observation set; page retries cannot double-count observations or omissions. Epochs older than 24 hours are superseded without closure reconciliation. Current transport reports fetcher_unavailable until isolated fetching is configured; there is no fallback to direct worker HTTP.
