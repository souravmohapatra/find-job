# Validation

## Current evidence

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
