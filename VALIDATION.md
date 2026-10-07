# Validation

## Current evidence

Authentication and profile ingestion/review now have real PostgreSQL/worker/browser validation under the approved host-network development setup. The current backend suite has 17 passing tests; seven frontend component tests pass. OpenRouter integration/model quality, collection, matching, notification and release gates below remain pending. See the dated evidence entries and PROGRESS.md for scope and commands.

## Historical documentation baseline

2026-10-07: documentation-only baseline. Workspace inspection found an empty repository working tree before this task. No application, containers, AI integration, collection engine, or notification flow exists. No product acceptance scenario below has been executed.

The initial ten-document baseline passed local link/whitespace checks. The previous implementation-design revision passed checks for 16 files. The broad-shortlist/daily-digest refinement receives a fresh document check recorded in PROGRESS.md. Technical selections are design decisions, not executed evidence.

## Future product acceptance scenarios

| Area | Expected observable outcome |
| --- | --- |
| Generic profile analysis | Synthetic CVs from different professions produce editable profiles without consulting/finance/entertainment assumptions. |
| Experience uncertainty | Overlapping dates, missing dates, and unclear roles do not become falsely precise experience claims. |
| User intent | Corrected experience and future preferences are distinguishable; changes persist. |
| Diversification | The same candidate can explore new sectors using transferable experience while explicit constraints still apply. |
| Collection independent of matching | An unsuitable or unassessed job remains accessible in the company's all-jobs view. |
| Company identity | Ambiguous names can be corrected before the wrong company is silently monitored. |
| Missing careers page | Discovery can retain the request and report no source honestly; it does not invent jobs or claim comprehensive absence. |
| Scheduled monitoring | Checks follow saved intervals and continue with the browser closed. |
| Persistence | Profile, requests, jobs, and prior notification state survive ordinary restarts. |
| Duplicate observations | Repeated observations do not create repeated new-job alerts. |
| Initial inventory | Existing listings appear with honest discovery/publication labels; initial alert behaviour follows the agreed policy. |
| Assessment quality | Explanations cite relevant listing/profile facts, preserve unknowns, and allow manual inspection of rejected results. |
| Profile changes | Stored assessments are refreshed or visibly identified as out of date under the chosen policy. |
| Failure visibility | Collection failure, partial coverage, AI failure, and delivery failure are distinguishable from no jobs or no match. |
| ntfy | Relevant events reach the configured local server; delivery failures are visible and recoverable. |
| Accessibility | Main journeys work with keyboard and narrow screens, with readable contrast, labels, and useful loading/error states. |
| Data handling | The user can understand where CV/profile data is processed; real private data is absent from tracked fixtures and logs used as evidence. |

Test tools and gates are selected below. Later validation must record what ran, results, limitations, and remaining gaps; a human-run checklist alone is not passed evidence.

## Implementation test strategy

- pytest unit tests: experience date unions, criterion policy, diversification, URL/content identity and lifecycle transitions.
- PostgreSQL integration tests: real Alembic and Procrastinate migrations, transaction rollback, unique intents, concurrent workers, stale revisions, duplicate observations and retention/purge rules. Do not substitute SQLite for these tests.
- Adapter contract fixtures: complete pagination, valid empty board, HTTP errors, changed/removed listings, JSON-LD, JS rendering and employer identity ambiguity. Fixtures are synthetic or minimal redistributable public samples.
- Vitest/Testing Library: profile draft conflict/recovery, visible status distinctions and all-jobs filter semantics.
- Playwright/axe: upload-to-review-to-company-to-job journey, keyboard-only navigation, responsive widths and accessibility checks. Automated scanning is supplemented by manual focus/screen-reader review.
- Compose integration: actual ntfy, worker kill/restart, AI failure, queue recovery, ambiguous send, partial crawl continuation, backup/restore and ingress isolation. Use isolated volumes and fake public-source endpoints; no live user CVs.
- Development source checks: use DEVELOPMENT_EXAMPLES.md, starting with all five user-named employers. Record discovered adapter type, actual bounded coverage and unsupported cases; no production subscriptions. Use a synthetic no-careers-page fixture and bounded live checks only during authorized development.

## Release gates

| Gate | Acceptance target |
| --- | --- |
| Deterministic invariants | All required invariant tests pass; no jobs lost by match filters, task retries or failed/partial source checks. |
| CV/extraction tasks | A few synthetic CVs from distinct professions and structured/unstructured synthetic job pages; verify extracted roles/dates and every cited fact, malformed/truncated input handling and no invented credentials. Include distinct per-task model configurations in the run record. |
| AI dataset | A small checklist of about 12 synthetic role/profile pairs covering partial overlap, new sectors, strategy analyst versus data analyst, legal practice, explicit must-haves and missing facts. Include another profession to prevent global function blacklists. |
| AI usefulness | Plausible strategy/adjacent roles at roughly 30-point overlap are shortlisted; clearly unrelated primary functions are excluded; both match and possible_match enter the digest. No numerical precision/recall target or ranking optimization is required. |
| AI evidence | Zero fabricated candidate qualifications in the evaluation; all required-criterion failures have valid cited evidence; all missing required facts remain unknown. |
| Task-model routing | Mock distinct models for profile_analysis, job_extraction and job_matching; prove correct routing, no account-default when unset, stale-config handling and recorded actual model. |
| Provider handling | Test schema/capability mismatch, model removal, 401/402/429/5xx, timed-out billed attempts, spend reservations, privacy restrictions and absence of API keys/raw CVs in logs or browser payloads. |
| AI behaviour check | Record chosen task models/settings and inspect basic category behaviour on the small example checklist. Investigate material contradictions without a repeated benchmark/tuning campaign; hosted outputs are not assumed deterministic. |
| Daily digest | One 19:00 local slot, configurable time/timezone, correct DST transitions, no duplicates after restart/edit, late assessments included next day, no off-schedule catch-up flood, and both shortlist categories included. Distinguish empty results from failed checks. |
| Development isolation | Example company seeds cannot populate production; named-company URLs are not treated as proven adapter coverage. |
| Private access | Allowed LAN/tailnet clients reach app/ntfy; unauthenticated clients cannot read private data; unintended host interfaces and backend ports reject ingress. Test IPv6 explicitly if enabled. |
| Fetch isolation | Private IPv4/IPv6, tailnet, metadata, redirects, DNS rebinding, subresources, direct-proxy bypass and fetcher-to-worker connections are blocked at runtime. |
| Recovery | Kill workers between persist/enqueue and send/ack boundaries; observe no lost job records, no routine duplicate alerts, and explicit unknown send state. Restore a backup with outbound actions disabled. |
| UX | Keyboard and narrow-screen core journeys pass; no serious/critical automated accessibility findings, plus manual focus/contrast/state review. |
| Performance | On the declared deployment hardware, inventory API p95 under 500ms for 10k jobs; 100 new complete listings assessed within two hours; measure application memory plus provider latency/cost before accepting sizing and budgets. |

The thresholds are selected acceptance targets, not observed results. Exact task models are deferred; final model evaluation waits for selection. If a chosen model misses the quality/performance gates, change that task's model/configuration and repeat affected checks. No silent model fallback is allowed. Record versions, commands, fixtures, hardware, timestamps and limitations with test results.

## Implementation evidence: backend dependency setup

2026-10-07: Approved package-registry sync with command-local SSL_CERT_DIR unset completed successfully (57 resolved / 55 installed); backend/uv.lock generated and parsed without embedded URL credentials. TLS remained enabled. Ruff lint, formatting and strict mypy passed for the current backend foundation. The isolated Compose PostgreSQL service started using its cached image and answered container-local SQL. Backend integration tests did not complete: host-to-container database handshakes timed out, and the initial waiting test run was interrupted. This does not pass milestone 1, authentication, migration or deployment acceptance. No frontend or full product validation has run.

## Implementation evidence: frontend foundation

2026-10-07: TypeScript + Vite production build, ESLint, six Vitest tests, and three Playwright tests passed. The unit coverage checks preserved destination after login, CSRF sign-out/cache removal, credential failure without losing form input, recoverable service failure, local form validation/password visibility, expiry cache clearing, and failed logout feedback. Browser journeys use installed Chrome at 375/768/1440 widths and mocked API routes; they check route focus, no page overflow, settings, login/logout and axe accessibility on login/workspace states. Zero axe violations detected in those checked states; this is not a complete WCAG audit. Desktop/mobile workspace screenshots inspected. Production build totals approximately 135 KB gzipped JavaScript and 3.1 KB gzipped CSS. API credentials and CV data were not used. Backend integration, Compose ingress and product flows remain unverified.

## Implementation evidence: development host-network database

2026-10-07: merged compose.test.yaml + compose.test.host.yaml configuration checked for host networking, absent port mappings/networks, and PostgreSQL command binding only 127.0.0.1:55439. Cached-image startup succeeded; host ss confirmed only the loopback listener. An authenticated psycopg connection from the host confirmed the database, configured listener, port and server address. The first check's raw inet text included /32; normalized with PostgreSQL host() and passed. `python3 scripts/test-backend.py -q`: seven tests passed, exercising the real PostgreSQL migration/authentication foundation. This replaces the earlier host-to-bridge blocker for development tests only. Normal Compose networking, LAN/tailnet ingress, fetcher isolation and full product behavior remain release gates on the intended deployment host.

Final backend recheck after migration timeout/configuration cleanup: Ruff lint/format, strict mypy, and seven PostgreSQL-backed tests passed (2.73s). One upstream httpx test-client deprecation warning remains. Digest-pinned merged Compose configuration passed inspection.

## Implementation evidence: profile ingestion and review

2026-10-07: 17 backend tests passed, covering the original authentication foundation plus profile review/immutable revisions, optimistic conflicts, duplicate upload/worker handling, real queue dispatch, expired operation leases and missing-worker queue recovery, TXT/DOCX tables/multi-page PDF parsing, unsupported/image-only/oversized input handling, evidence validation, deletion/purge, and retained/pending-document protection during 30-day retention. Ruff lint/format and strict mypy passed; readiness's dynamic Alembic-head check passed its targeted regression test. One upstream Starlette/httpx deprecation warning remains.

Seven frontend component tests, TypeScript/Vite build, ESLint and Prettier passed. The new profile test verifies that a conflicting save retains edits and domain choices and focuses its error. The Playwright real-backend journey passed in 45.5s using a separate disposable database and actual API/worker/parser: synthetic CV upload, reviewed profile activation, reload persistence, domain diversification and a later preference edit. It checked 375/1440 widths, no page overflow and zero axe violations on the tested editor states. Desktop screenshot reviewed; fixture servers exited afterwards. This is local application evidence with mocked inference, not a live model evaluation or production Compose-network test.

The user-provided real local PDF passed the bounded parsing-only utility: one page with text, 3,847 extracted characters. No extracted text was persisted or printed, no AI requests occurred, and the original is ignored by Git. Reading order and factual extraction have not been semantically assessed. Synthetic automated tests cover additional formats so this file is not a parser template or committed fixture.

Remaining profile obligations include live provider implementation tested with mocked transports, task-model Settings, complete profile data-management controls and further replacement/conflict UX checks. All remaining PLAN.md milestones and deployment-host gates remain required.

2026-10-07 format follow-up: the supplied PDF again passed aggregate-only local extraction (one page, 3,847 characters; no AI requests). The backend suite now passes 18 tests, including a synthetic DOCX with interleaved headings/tables, a nested table and merged cells. Verified original body order, nested text presence and absence of repeated merged-cell text. Ruff lint/format and strict mypy pass. This does not establish arbitrary PDF column order, OCR support, header/text-box coverage or model extraction quality.

## OpenRouter settings and provider slice

2026-10-07: PostgreSQL-backed synthetic HTTPX tests cover independent task revisions, optimistic settings conflicts, secret-file presence without secret disclosure, captured model IDs, consent across mode changes, structured request privacy/price constraints, explicit model fallback provenance, evidence and omitted-field rejection, one charged repair attempt, provider errors, persisted Retry-After, concurrent daily-budget/concurrency admission, unknown-cost holds across days, interrupted reservations and generation metadata reconciliation. No authenticated OpenRouter request or real CV inference was made. The endpoint/price fixtures are synthetic; actual model/provider compatibility remains a live acceptance gate.

Eight frontend tests pass, including model-edit preservation and focused errors after conflict, plus retention of edits during a background settings refresh. TypeScript/Vite build (about 146.1 KB gzipped JavaScript / 3.9 KB CSS), ESLint and Prettier pass. The real API/PostgreSQL/worker Playwright suite passed both profile and Settings journeys (1.4 minutes). Settings save/reload, task independence, ZDR choice, budget persistence and explicit mock validation were verified. Targeted rechecks passed after advanced-control spacing and unset-temperature corrections (last Settings run 54.3 seconds). Checked 375px and 1440px layouts with advanced controls expanded, no horizontal overflow and zero axe violations in those states; desktop and mobile screenshots inspected. This is not a complete accessibility audit.

Alembic `check` reported `No new upgrade operations detected.` New migration bootstrap also passed against the disposable browser database. Library-owned queue tables are excluded from autogeneration. Ruff and strict mypy pass. Synthetic date/phone regression verifies that contact minimization preserves ISO date ranges, year ranges and separate date lines while removing the example phone/email. Billing-recovery UI, handling verified billing without a generation ID, richer analysis fixtures and profile deletion/conflict UX remain incomplete; no milestone 2 or release completion is claimed.

Final backend run after contact-minimization changes: `python3 scripts/test-backend.py -q` passed **42 tests in 8.86s**, with the existing upstream Starlette/httpx deprecation warning only. Ruff lint/format and strict mypy pass. Browser fixture ports 8000/5173 have no listeners after teardown; the authorized development database remains running.

2026-10-07 profile data management: added backend regressions for authenticated document metadata, retention updates, cancellation, deletion/download availability and monotonically increasing revisions across purge/recreation. Full backend suite passed 44 tests, then the 25-test AI suite passed after adding cancellation checks at request admission. The real data-management browser journey passed (3.1s; 8.1s with fixture startup), including persisted retention, single-original removal preserving reviewed facts and typed-confirmation full purge. At 375/1440 widths, checked zero axe violations and no overflow; desktop screenshot inspected. Nine frontend tests pass, including retention rollback on failed save. TypeScript/Vite build, ESLint, Prettier, Ruff and strict mypy pass. Initial browser failures were a sign-in/setup race (HTTP 401) and delayed checkbox state; both corrected and revalidated. Existing upstream Starlette/httpx deprecation warning remains. These checks use only synthetic documents.

Final profile regression run: 13 tests passed (4.42s), including retention/cancellation and purge/recreate conflicts. Final Ruff lint/format and strict mypy pass. Frontend fixture ports 8000/5173 are no longer listening after teardown. The original dependency/network boundaries remain unchanged.

2026-10-07 conflict recovery: fourteen profile backend tests and eleven frontend tests pass. New coverage checks both profile/draft expected versions, evidence rejection during reconciliation, no premature activation, local edit preservation during refresh, explicit merge choices and cross-CV provenance handling. TypeScript/Vite build, ESLint/Prettier, Ruff and strict mypy pass. The original upload/review browser journey passed (29.0s); the isolated conflict journey passed (9.8s, 18.1s with fixtures), persisting local summary plus chosen saved goals after renewed confirmation. At 375/1440 widths: no overflow and no axe violations on comparison states; desktop screenshot inspected. An earlier browser timeout followed two unexpected full document reloads during concurrent frontend changes/tests; subsequent isolation avoids counting such a run as application evidence. The draft merge is covered by real API and editor-component tests; a combined browser draft-conflict journey remains useful for final release coverage.

2026-10-07 local CV recheck: aggregate-only parsing again returned one page and 3,847 characters, zero AI calls and no persisted extracted content. Git-ignore check passed. This is extraction evidence only, not reading-order or semantic acceptance. Pending billing changes: 27 AI backend tests passed; API schema generation and TypeScript/Vite build passed after correcting an uninitialized React useRef argument. Billing interaction/browser coverage remains pending.

Billing recovery final local evidence: 48 backend tests, 12 frontend tests, generated contracts, TypeScript/Vite build, ESLint/Prettier, Ruff lint/format and mypy pass. Real API/database browser recovery passed in 10.5s (21.9s total), recording a synthetic verified cost without another AI call; 375/1440 widths have no overflow or axe violations. Mobile screenshot inspected. No live provider acceptance is claimed.

ATS decoder foundation: 14 synthetic tests pass, plus Ruff lint/format and strict mypy. Covers Greenhouse complete/empty/count mismatch, Lever global/EU pagination and full descriptions, Ashby listing visibility/locations/compensation, duplicate/malformed rows, safe stored links and meaningful revisions. No live source, scheduling, durable inventory or network-isolation acceptance is implied.
