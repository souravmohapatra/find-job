# Progress and continuation

Historical private-registry endpoints in this document are anonymized as `packages.example.invalid`; this is not a working package source.

Updated: 2026-10-07.

## Current state

Implementation is active. Authentication, generic CV/profile review, OpenRouter task settings/accounting and company/source/job inventory have local synthetic validation. The portal supports company controls and unfiltered job browsing; collection epochs and scheduling have PostgreSQL-backed tests. The new separate HTTP fetcher and worker client have mocked transport coverage and remain disabled until deployment network isolation is validated. Browser fetching/discovery, matching, ntfy, fuller inventory UX, backup/restore and production/live acceptance remain unfinished. No end-to-end live monitoring claim is made. Normal Docker bridge networking still requires the intended deployment server.

## Host-network development alternative — 2026-10-07 (verified)

The user authorized a development-only PostgreSQL host-network alternative, with PostgreSQL explicitly restricted to 127.0.0.1:55439. Added compose.test.host.yaml as an opt-in override of the disposable test database, removing port mappings and setting both server and health-check ports explicitly. Normal compose.yaml deployment architecture is unchanged.

Verified the merged configuration specifies host networking, no port mappings/networks, and the exact PostgreSQL listen address/port. Stopped the old disposable bridge test container to release the port, then ran:

```sh
docker compose -f compose.test.yaml -f compose.test.host.yaml up -d --wait --pull never db
```

The service became healthy from the cached PostgreSQL image. `ss -ltn 'sport = :55439'` showed only `127.0.0.1:55439`; Docker inspection returned network mode `host`. An authenticated host psycopg connection succeeded using the unchanged test endpoint. SQL verified listen_addresses=127.0.0.1, port=55439, server address=127.0.0.1 and current database=jobfinder_test. The first address assertion failed because PostgreSQL rendered the inet value as `127.0.0.1/32`; using `host(inet_server_addr())` normalized it and the corrected assertion passed. This was a verification-format issue, not a connection failure.

`python3 scripts/test-backend.py -q` completed with **7 passed in 1.33s**, covering initial migration, private routes, owner creation protection, login/session/logout, CSRF/origin checks, session rotation/expiry, durable throttling and production security settings. The existing FastAPI/Starlette test-client integration emits an httpx deprecation warning; it did not fail the tests. Added explicit Alembic path splitting and a migration connection timeout so migration startup is bounded as well as application connections. Pinned the test database to the digest of the cached, tested image. Corrected the development secret generator to write a newline for newly created secrets; existing secrets were preserved.

Final validation after the timeout/configuration cleanup: Ruff lint/format and strict mypy passed; backend tests passed again (7 passed, one upstream test-client deprecation warning, 2.73s). The digest-pinned merged Compose configuration passed inspection. Backend authentication/migration source, tests, test Compose files and development scripts were committed as 2588a5a; production Compose/image scaffolding remains outside that validated slice.

The host-network alternative is now verified for development database access and the current backend tests. It does not fix the Docker bridge, validate service-to-service networking or prove production deployment/isolation. No VPN, firewall, host routes, global certificate settings or credentials were changed. The disposable database remains running in host-network mode for further development. Re-run normal Compose networking, private ingress and fetcher isolation checks on the intended Ubuntu server before deployment. The old bridge-blocker evidence below is retained as history; backend development is no longer blocked on it.

## Previous checkpoint: Docker/database blocker — 2026-10-07

Implementation is blocked on the development host's Docker database connectivity. This entry records the actual outputs from the preceding implementation checks; no new network probe or dependency retry was run for this documentation update.

### Completed and saved

- `36d391a`: backend dependency manifest/lockfile and validation evidence. The authorized package-registry retry succeeded with TLS enabled and SSL_CERT_DIR unset for that process only.
- `306aa64`: frontend authentication/navigation foundation. Production build, lint, formatting, six component tests and three mocked browser journeys passed. These do not prove backend or full product behavior.
- Backend source passes Ruff and strict mypy, but its authentication/migration runtime tests have not completed. Backend source and initial Compose/deployment scripts remain uncommitted pending runtime validation.

### Actual failure and supporting evidence

Docker image pulls and test-container startup succeeded. The failure is the host application's PostgreSQL connection to the Docker container, not a failed Docker pull or startup command.

Startup command:

```sh
docker compose -f compose.test.yaml up -d --wait --pull never
```

It exited successfully and reported `Container jobfinder-test-db-1 Healthy`. Subsequent `docker compose -f compose.test.yaml ps` showed the service healthy, exposing `127.0.0.1:55439->5432/tcp`.

The initial test command was:

```sh
python3 scripts/test-backend.py -q
```

It stalled opening the database connection for the initial Alembic migration. It was explicitly interrupted after approximately 79 seconds; no tests completed. The relevant test output was:

```text
KeyboardInterrupt
<repository>/backend/.venv/lib/python3.12/site-packages/psycopg/connection.py:118: KeyboardInterrupt
2 warnings in 79.24s (0:01:19)
```

Separate bounded `psycopg.connect(..., connect_timeout=5)` probes to each of `127.0.0.1:55439` and `172.19.0.2:5432` raised `psycopg.OperationalError`; the captured error text for each was exactly:

```text
connection timeout expired
```

Container-local `psql` successfully queried PostgreSQL. A host TCP socket connection to the published port succeeded, but the PostgreSQL handshake did not. The database activity query showed only the container-local diagnostic query, with no host client session.

Read-only routing checks produced these relevant fields:

```text
$ ip route get 172.19.0.2
172.19.0.2 dev cscotun0

$ ip -br address show br-5adb41e90655
br-5adb41e90655  DOWN  172.19.0.1/16
```

The route excerpt omits the host source address and user ID. Docker network inspection identified subnet `172.19.0.0/16`, gateway `172.19.0.1`, and container address `172.19.0.2`. These observations locate a routing/bridge problem; they do not establish why the bridge is down or prove that the VPN caused it.

### Pending action and preserved state

User assistance is needed to restore the host-to-test-container network path. No VPN, firewall, host route, or Docker daemon configuration has been changed. The isolated `jobfinder-test-db-1` container was left running for diagnosis; its data is temporary and separate from production. Added ten-second database connection/pool timeouts in the uncommitted backend so future application attempts fail promptly.

After the network path is restored, verify a bounded database connection, rerun backend migration/authentication tests, and continue milestone 1's integrated Compose validation. Do not repeat the completed dependency setup or claim the full application is ready. The active implementation goal is marked blocked awaiting this external change.

## Active work: profile ingestion and durable operations

The user requested continuing PLAN.md to completion. Foundation source and development SQL connectivity are validated; production Compose networking remains a deployment-host gate under the approved exception. Next slice: bounded private CV parsing, evidence-backed editable drafts, immutable reviewed revisions with concurrency checks, and durable operation intents/worker handling. Development uses synthetic documents and mock inference; no live paid API calls. No profile acceptance gate has passed yet.

## Completed

- Initial product/context baseline and personal-project/local-Git guidance.
- Selected focused app over full platform fork, with public-documentation evidence and limitations.
- Selected React/FastAPI/PostgreSQL/Procrastinate, isolated HTTP/browser collection, OpenRouter per-task routing, ntfy and private Caddy/Tailscale entry points.
- Specified schema concepts, immutable revisions, API contracts, task durability, retries and lifecycle rules.
- Specified CV review, domain diversification, explainable matching and reassessment defaults.
- Specified UI, authentication, secret handling, notifications, backups and acceptance gates.
- Updated earlier high-level-only/deferred decisions to match the latest authorization.
- Incorporated OpenRouter steering across deployment, data model, Settings, budgets, provenance and validation; removed local-model hardware assumptions.

## Latest product refinement

The user supplied Netflix, Spotify, Amazon, Revolut and Airwallex as development-only examples, requested roughly 30% relevance with manual review and exclusion of unrelated primary functions, and selected a configurable daily 19:00 summary. Added supplementary entertainment/finance/corporate/consulting examples with public career entry points. Replaced strict matching/precision gates, made both shortlist categories digest-eligible, and specified timezone/DST/late-assessment behaviour. No app code or runtime work occurred.

## Verification

2026-10-07: checked all 16 Markdown documents, 38 local links, balanced code fences, trailing whitespace and final newlines. Confirmed all three task-model keys are specified, no obsolete Ollama/Qwen selection remains, and no local inference service appears in the deployment. Manually reviewed cross-document scope, privacy, task state, retry and network decisions. No product or runtime acceptance gate has run.

Public official documentation and repository READMEs informed the plan. External pages are references, not proof that our eventual configuration works. Model quality, supported-site coverage, resource estimates and private-network enforcement still need implementation tests.

2026-10-07 refinement check: all 17 Markdown documents and 41 local links passed; code fences, whitespace and final newlines checked. Confirmed the five user-named companies, broad 30-point policy and 19:00 daily digest; stale frequent-digest and strict-precision defaults were removed or explicitly marked superseded. Public career entry points were checked, but no collection or matching runtime was tested.

## Next authorized boundary

Continue implementation milestone 1 using the verified development-only host-network test override. Normal production-network validation remains deferred to the intended Ubuntu server. Local implementation, dependency setup, container runtime and validation are authorized; retain the dependency-failure boundary in AGENTS.md.

## Resume notes

Read AGENTS.md, CONTEXT.md, DECISIONS.md and IMPLEMENTATION.md. Exact models are intentionally unset; profile_analysis, job_extraction and job_matching must be configured independently before their LLM tasks run. No local LLM infrastructure is planned. Brave requires a deployment key for automatic company-name discovery; direct URL monitoring can work without it. Domain diversification defaults open but is visibly editable. “All jobs” includes unassessed and rejected jobs. Notification success means ntfy acceptance, not device display. Preserve unknown/partial/error states and no-public-ingress boundaries.

## Development readiness (historical pre-implementation checks)

The current workspace is the development environment. Read-only checks found Ubuntu 24.04, accessible Docker/Compose, Python 3.12 and Node 22, with adequate available memory/disk for the planned containers. No package installation or container build/start was performed.

The user supplied npm's configured package-registry registry. Earlier direct public-registry TLS timeouts bypassed npm configuration and do not prove the configured npm route is broken. Actual package installation through the configured proxy remains unverified; do not silently replace it with the public registry.

Development will use mocked OpenRouter and search responses; the user will provide an OpenRouter key and choose task models for final live validation. A non-empty BRAVE_API_KEY is now present in local .env; only the variable name/presence was checked, never its value in output, and no authenticated request was made. Added .gitignore exclusions for local environment files while retaining placeholder example files.

No additional host package installation is identified as a prerequisite to starting implementation. uv, project dependencies and test browsers will be provisioned in the development/test containers. Tailnet/client notification validation still requires Tailscale and a separate client later.

## Implementation authorization

The user requested implementation, validated phase commits and blocker escalation. Local dependencies, project containers and test execution are now in scope. Mocks remain the default; no live paid requests. Phase 1 is starting with migration/authentication/UI/development infrastructure.

## Dependency blocker during phase 1 (historical; resolved below)

The configured npm proxy passed npm ping. Backend foundation code, authentication tests and migration/Compose files have been created, but they are unvalidated and uncommitted. `uv sync --project backend` failed fetching `https://pypi.org/simple/lxml/` with `invalid peer certificate: UnknownIssuer`. No certificate/registry workaround or retry was attempted.

The user clarified that this development environment is on a restricted development network: failed dependency fetch/sync/image pulls must be reported as blockers rather than worked around. This rule is now in AGENTS.md. Await user-provided dependency/network configuration before resuming installation. The validated planning baseline is committed as a8e8986; do not represent the unvalidated implementation as a completed phase.

The already-running image pulls finished successfully for postgres:17-alpine, python:3.12-slim, node:22-alpine and caddy:2-alpine. No download process remains pending. The current blocker is Python/uv certificate trust.

## Approval-review blocker on the authorized retry (historical; resolved below)

The goal-resume instruction specified one retry through the package-registry Python index, preserving TLS and existing .netrc credentials, and a second attempt with SSL_CERT_DIR unset only if the first returned UnknownIssuer. Automatic approval review rejected the first command before execution. After checking the existing rule's exception for new user instructions, the same command was resubmitted with explicit reference to the resume authorization; review again rejected it because it did not recognize that authorization as a user message. Neither dependency attempt executed. No credentials were displayed or modified, no TLS settings changed, and no further network attempt was made. Asked the user to provide the authorization in ordinary chat so review can recognize it. Backend implementation remains unvalidated and uncommitted.

Manual approval subsequently allowed the exact first package-registry command to run. It exited 2 fetching `https://packages.example.invalid/python/simple/mypy/`: `client error (Connect)` / `invalid peer certificate: UnknownIssuer`. The conditional second command (`env -u SSL_CERT_DIR ...`) was submitted but automatic approval review rejected it before execution, stating that manual approval covered only the first exact command. The second dependency attempt has not run. No global settings or credentials were changed. Await recognizable approval for the exact conditional command; no alternate command or registry will be tried.

## Dependency recovery and database validation blocker

Specific manual approval subsequently allowed the conditional second attempt to execute. With SSL_CERT_DIR unset for that command only, package-registry sync succeeded: 57 packages resolved, 55 installed, backend/uv.lock generated. TLS verification remained enabled; .netrc and global settings were untouched. The prior approval and Python trust blockers are resolved for this completed setup attempt.

Ruff check and format checks pass; strict mypy passes for all eight current app files. Parsed the lockfile and checked package artifact URLs for embedded credentials: none present. These are dependency/static checks, not application acceptance.

Started the dedicated Compose test PostgreSQL container with `--pull never`; it is healthy and accepts SQL through container-local psql. Host TCP connection establishment to 127.0.0.1:55439 succeeds, but psycopg SQL handshakes to that address and to container bridge 172.19.0.2:5432 each expire with `connection timeout expired` under a five-second connect timeout. No host client appeared in pg_stat_activity. Interrupted the original pytest run while waiting for its initial migration connection; no tests completed. Added a ten-second connection/pool timeout to the application to avoid indefinite hangs. No Docker/firewall/network settings were modified. The isolated test container remains running for diagnosis; its database uses tmpfs and is separate from production data. User assistance is needed with the host/container network boundary before runtime validation can resume.

## Frontend foundation validated independently

The configured npm proxy installed 298 packages and generated frontend/package-lock.json. No registry change was made; no embedded credentials appear in lockfile URLs. Implemented responsive sign-in, session loading/error/retry, CSRF-aware sign-out, route-preserving navigation, private-cache cleanup on logout/expiry, and explicit development-preview pages. CV upload, monitoring, matching and notifications are not implemented by this shell. Applied the ui-ux-pro-max guidance already selected in UI_UX.md, including keyboard labels/focus, accessible authentication, reduced motion and responsive layout.

Validation passed: TypeScript/production Vite build, ESLint, six Vitest component/behavior tests, and three Playwright Chrome journeys at 375/768/1440 widths. Browser checks include sign-in, navigation focus, settings, CSRF sign-out, no horizontal page overflow, and zero axe violations on the checked login/workspace states. Inspected desktop and mobile screenshots. Browser API responses are mocked; none of these results validate backend authentication, private deployment or the full job-finding journey. Test servers terminated normally; screenshots remain ignored under frontend/test-results/.

Read-only routing diagnosis narrowed the backend blocker: `ip route get 172.19.0.2` selects cscotun0, while Docker's br-5adb41e90655 interface for 172.19.0.0/16 is DOWN. This is evidence of a routing/bridge problem, but does not establish why the bridge is down or prove that the VPN caused it. No VPN, routes or firewall settings were changed. User assistance is still needed at that boundary.

### Profile slice checkpoint

Implemented domain-neutral facts/preferences, private uploads, bounded parser subprocess, draft review and activation, immutable revisions/If-Match conflicts, document deletion/purge, operation status/retry, and a Procrastinate dispatcher with leases and duplicate protection. Current automated result: 15 backend tests pass, including the real queue and expired-lease recovery. Profile analysis is still an explicit minimal mock, not a live model implementation; reassessment handling and AI configuration remain to be implemented. The profile UI is next. No milestone 2 completion claim yet.

The user provided a real local PDF for parser testing. Added its path to .gitignore and a local check-cv.py utility that reports aggregate metrics only. The bounded parser extracted one page / 3,847 characters successfully; no extracted content was persisted or logged and no AI call was made. This is parsing evidence, not a semantic accuracy or layout-order review. Committed tests remain synthetic and cover distinct professions, TXT, DOCX tables and unreadable/image-only PDF rejection.

### Profile workflow validation checkpoint

The current profile slice passes 17 backend tests, including PostgreSQL/Procrastinate schema startup, real queue dispatch, operation lease recovery, stalled queue-job reconciliation through supported library APIs, idempotent uploads, conflicting immutable revisions, evidence rejection, local format limits, DOCX tables, multi-page PDF text, explicit deletion/purge and approved-document retention. Pending or retained originals are not auto-deleted. Ruff and strict mypy pass. A real browser journey against a separate disposable jobfinder_test_browser database completed upload → actual local parser/worker → profile review → activation → reload → preference edit, using a synthetic designer CV and mock inference. It checked 375px/1440px layouts, no horizontal overflow, and no axe violations on checked editor states; desktop screenshot inspected. These checks do not validate live model quality or production networking.

Added a frontend conflict-recovery test that retains edited summary/domain choices on 409 and focuses the error. Initial test issues were a fixture missing generated required fields and a radio name that included helper text; corrected the fixture and separated the radio label from its accessible description. Final UI checks passed: seven Vitest tests, TypeScript/Vite build, ESLint, Prettier, and the real backend browser journey (45.5s). A final backend readiness regression check passed after switching readiness to the actual Alembic head. Browser API/worker/Vite processes exited cleanly; only the existing development database remains running. OpenAPI now generates the profile/operation TypeScript contracts rather than maintaining those types manually. Real CV data remains excluded from fixtures and Git.

Remaining milestone 2 work: OpenRouter task settings and real provider implementation (with mocked transport tests), richer mock analysis fixtures, UI data deletion/retention controls, and complete conflict recovery/comparison polish. Profile reassessment intents are persisted but their handler intentionally reports unavailable until the inventory/matching stages are implemented. Milestone 1 also retains container-build/private-ingress gates. The implementation goal remains active, not complete.

### Supplied CV and format variation follow-up

2026-10-07: Re-ran `backend/.venv/bin/python scripts/check-cv.py SouravMohapatraCV.pdf`: success, one page / 3,847 characters, no persisted extracted text and zero AI requests. `git check-ignore` confirms the file is excluded. This remains extraction-only evidence; semantic accuracy and PDF reading order are not established.

Fixed DOCX traversal to retain paragraphs and tables in body order, include nested table content and avoid repeating merged cells. Added a synthetic teacher CV regression through the actual upload/parser worker path, checking section order, dates, nested content and deduplication. No real CV content was added to tests. All 18 backend tests pass (one existing upstream Starlette/httpx warning), Ruff lint/format pass and strict mypy passes. An initial Ruff I001 import-order failure was corrected; it did not affect the passing runtime suite. Text PDFs, DOCX and UTF-8 TXT are supported within documented limits; OCR and arbitrary-layout fidelity are not claimed.

The initial read-only shell command `pwd && git status --short` failed before execution with exit 1: `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`. Approved escalated commands allowed normal work to continue; no network or dependency configuration changed. OpenRouter task settings/provider implementation remains the next planned slice; the overall implementation goal is unfinished.

### OpenRouter integration checkpoint

Implemented unvalidated per-task configuration revisions, secret-file-only provider access, strict-schema requests, endpoint/pricing checks, transactional call/spend reservations, consent-bound profile ingestion, synthetic validation operations and generation-cost reconciliation. All outbound behavior will be tested with HTTPX MockTransport before any live acceptance. Reviewed the generated migration before execution: Alembic attempted to include deletions of library-owned Procrastinate tables; removed those unexecuted changes and excluded those tables from future autogeneration. No queue tables were dropped. Initial static checks exposed formatting/type issues; corrections and behavioral validation are underway. No milestone completion claim yet.

AI checkpoint: 39 backend tests now pass, including synthetic HTTPX requests, independent settings/optimistic conflicts, immutable queued model choice, fallback privacy, two-attempt schema repair, evidence rejection, 401/402/404/429/503 handling, persistent Retry-After, concurrent budget reservations, timeout/unknown-cost holds, metadata reconciliation, and mock-to-live consent protection. Eight frontend tests pass, including preserving model edits on conflict and background refresh. Fixed a reconciliation test seam that still called the production client factory (mock mode correctly prevented outbound access), missing conflict feedback, and JSX/type/format issues. The real API/worker browser suite is still running; do not count it as passed yet. No live provider calls or real CV inference occurred.

### Model Settings/provider slice validated locally

Per-task models, explicit fallback/provider choices, optional ZDR, token/time/price ceilings and daily budgets are now editable in Settings. Saving does not call OpenRouter; explicit synthetic validation runs through the durable queue. The UI retains model edits on conflicts/background refresh and distinguishes mock-only validation from live provider checks. Profile uploads capture immutable model configuration, mode and consent; AI facts must contain valid quotations and cannot claim user authorship or set a years-of-experience override. Contact minimization now preserves dates and separate lines rather than mistaking them for phone numbers.

Eight Vitest tests, TypeScript/Vite build, ESLint and Prettier pass. Both real API/worker browser journeys passed (1.4m); subsequent targeted advanced-control/temperature checks passed at 375/1440 widths with no overflow or axe violations (last run 54.3s). Inspected desktop/mobile screenshots. Alembic consistency check passed and fresh browser DB migration succeeded. Static backend checks pass. No live API requests were made; real CV contents remain excluded from Git and inference.

Resolved check failures: `npm --prefix frontend exec -- prettier ...` initially returned `No files matching the pattern were found` because paths were relative to the root; used the installed executable with repository-relative paths. Initial TypeScript check reported TS18048 on optional generated fallback/provider arrays; defaults now handle absent arrays. JSX had an invalid closing option tag, corrected before runtime. The conflict-refresh test initially lacked visible refresh feedback; fixed without discarding edits. The first redaction patch triggered Ruff B023 (loop closure) and E501; replaced placeholder callbacks with date-preserving split traversal and corrected formatting. None was a dependency/network failure.

Remaining work before finishing milestone 2: billing-recovery UI/verified resolution for unknown requests without generation IDs, profile deletion/retention controls, complete profile conflict recovery, and richer synthetic analysis fixtures. Live model quality remains gated on user-supplied key/models; inventory/matching/digest/production deployment milestones remain in scope. Next continue those UX/recovery pieces, then company inventory and scheduled ATS collection. The overall goal is active and unfinished.

Final backend run after contact-minimization changes: `python3 scripts/test-backend.py -q` passed **42 tests in 8.86s**, with the existing upstream Starlette/httpx deprecation warning only. Ruff lint/format and strict mypy pass. Browser fixture ports 8000/5173 have no listeners after teardown; the authorized development database remains running.

### Profile data-management checkpoint

Continued after validated provider commit `0d26e8e`. Added paginated original-document metadata, retention editing, confirmed original removal and explicit full-profile deletion in the UI. Deletion clears cached raw draft data and cancels unfinished ingestion; AI reservation admission now checks operation cancellation before another request. Original removal preserves draft/reviewed facts, while full purge removes them. Profile revision counters now remain monotonic across purge/recreation, preventing an old editor from accidentally reusing a new profile's revision number. Added backend and browser regressions; validation is in progress.

Data-management check results so far: 44 backend tests passed before the cancellation-admission change; the 25-test provider suite passed afterward, including the new cancellation guard. Eight frontend tests, build, lint and format checks passed. The first new browser journey failed during synthetic API setup: PATCH /api/v1/profile returned 401 because the test read session state before asynchronous sign-in completed. Updated the test to wait for the authenticated CV control. Also corrected purge success text and cancelled-draft/download visibility. Browser revalidation is pending.

### Profile storage controls validated

The final data-management browser journey passed (3.1s; 8.1s including fixture startup): authenticated retention change persisted across reload, original download became unavailable after confirmed removal while reviewed facts remained, full purge required typed confirmation, and profile/draft/document APIs returned the cleared state afterward. Checked 375/1440 widths without overflow or axe violations; desktop screenshot inspected. Fixed a real interaction issue exposed by the browser: a server-controlled retention checkbox briefly reverted while saving. It now updates immediately, waits for persistence, and rolls back on failure. A focused component test verifies rollback without clearing existing draft data.

Nine frontend tests, production TypeScript/Vite build, ESLint and formatting pass. Backend full suite passed 44 tests before the added cancellation admission guard; the 25-test AI suite then passed with that guard. Final profile regression/static checks are recorded below. Remaining milestone 2 work is full profile conflict recovery and billing-recovery UI/verified unknown-cost resolution, plus richer synthetic analysis fixtures; live acceptance still awaits chosen models/key. The main monitoring/matching/digest/deployment milestones remain unfinished. No live API or real-CV inference occurred.

Final profile regression run: 13 tests passed (4.42s), including retention/cancellation and purge/recreate conflicts. Final Ruff lint/format and strict mypy pass. Frontend fixture ports 8000/5173 are no longer listening after teardown. The original dependency/network boundaries remain unchanged.

### Profile conflict recovery checkpoint

Continued after storage-controls commit `9b41c19`. Added an explicit comparison workflow that preserves the editor's original revision across background refreshes, presents local/saved-profile/saved-draft field choices, and requires renewed review before saving. The new draft reconciliation endpoint checks both current profile revision and draft version under the profile lock, validates evidence and does not activate the draft. Copied approved-profile facts are treated as owner-confirmed corrections when the source CV differs. Fourteen profile backend tests, ten frontend tests, strict mypy, Ruff, TypeScript/Vite build and ESLint pass so far. Real-browser and additional draft-provenance checks are in progress; no completion claim yet.

Conflict browser check: the original upload/review journey passed (29.0s), but the conflict journey timed out at the comparison confirmation checkbox after the editor disappeared. Trace inspection showed two unexpected document GET /profile reloads (19:09:15 and 19:09:16 UTC), with Vite reconnecting each time, during overlapping frontend test-file changes/Vitest execution. This is observed test interference; it does not yet prove the isolated application flow passes. Re-run with frontend files/processes held stable. The additional draft-provenance component test passed, bringing the frontend suite to eleven passing tests.

### Profile conflict recovery validated

Fourteen backend profile tests pass, including stale profile/draft revision rejection, mandatory comparison acknowledgment, evidence validation, draft-only reconciliation and subsequent activation. Eleven frontend tests pass, including background-refresh edit preservation, explicit per-field merge choices, renewed confirmation and clearing foreign-CV citations when copying approved facts into a replacement draft. TypeScript/Vite build (about 148.8 KB gzipped JS / 4.1 KB CSS), ESLint, Prettier, Ruff and strict mypy pass. One generated-contract fixture initially omitted required document_available and caused TS2741; the fixture was corrected and the production build rerun successfully.

The original real upload/review browser journey passed (29.0s). The isolated conflict browser journey passed (9.8s; 18.1s with startup), proving a retained local summary, selected remote goals, renewed review and a new persisted profile revision. At 375/1440 widths the comparison had no horizontal overflow or axe violations; desktop screenshot inspected. The earlier timeout coincided with unexpected Vite document reloads during overlapping frontend work, and did not recur with an isolated run. Added that isolation rule to AGENTS.md. No live API calls or real-CV inference occurred.

Remaining milestone 2 follow-up: billing-recovery UI and verified unknown-cost resolution, plus richer synthetic analysis fixtures and final live acceptance. Company inventory/scheduling, generic discovery, matching, ntfy and deployment gates remain part of the active goal.

### Local CV confirmation and pending billing validation

2026-10-07: Reconfirmed the supplied PDF with the aggregate-only `scripts/check-cv.py` utility: one page, 3,847 characters, no persisted extracted content and no AI requests. Git ignores the original. It is an example, not a parser template; existing synthetic coverage includes PDF, TXT and DOCX body/table order. Arbitrary PDF column order and semantic accuracy remain unverified; OCR is unsupported.

The initial shell inspection again failed before execution with exit 1: `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`; approved escalated inspection succeeded without network changes. Collected pending billing-check results: API contract generation passed and 27 AI backend tests passed (8.95s, existing upstream deprecation warning). The frontend build failed with `src/features/settings/billing.tsx(34,21): error TS2554: Expected 1 arguments, but got 0.` Supplied the required initial useRef value; build revalidation follows. Billing controls and provenance remain uncommitted and need further validation. The overall implementation goal remains active.

Frontend TypeScript/Vite build passed after the useRef initialization correction (150.62 KB gzipped JavaScript). This resolves that build failure; billing browser/interaction validation remains pending.

### Billing recovery validated locally

Added request accounting history, unresolved reservation recovery, queued provider metadata lookup and confirmed owner-verified cost entry. Stored provenance distinguishes provider reports, owner verification, rejected requests and legacy records. Resolution never retries inference; stale/repeated owner writes return conflicts. Unknown reservations remain held until resolved.

Validation: 48 backend tests passed (27.88s; existing upstream deprecation warning), 12 frontend tests passed, API generation, TypeScript/Vite build, ESLint, Prettier, Ruff lint/format and strict mypy passed. The real browser recovery journey passed (10.5s; 21.9s including startup), using one synthetic unknown request in the fixed disposable database. It verified required confirmation, persisted 0.25 owner-verified cost, released hold and no new inference. At 375/1440 widths: no horizontal overflow or axe violations; mobile screenshot inspected. No live API calls or private CV inference occurred.

Next: company/source inventory and scheduled ATS collection. Richer synthetic profile analysis fixtures and live acceptance remain open, along with discovery, matching, ntfy, production Compose/ingress/isolation and final release gates. Deployment scaffolding remains unvalidated; the full goal remains active.

### ATS decoding foundation

Billing recovery saved as local commit `34cc00c`. Started milestone 3 with transport-independent Greenhouse, Lever and Ashby request/normalization contracts, checked against the official public API documentation. Source metadata includes full plain-text descriptions, canonical links, locations, published dates where supplied, workplace/employment labels and salary data. Collection has no profile dependency or match filtering. Lever handles global/EU hosts and explicit continuation offsets; duplicate/invalid postings or unverifiable counts prevent complete-inventory claims. Ashby excludes explicitly unlisted posts. Tracking parameters are removed conservatively while meaningful job parameters remain.

Fourteen synthetic adapter tests pass (1.97s), including empty versus malformed inventories, continuation, duplicate/invalid rows, unrelated job functions, nested description sections, salary/location normalization, meaningful content hashing and obvious unsafe-link rejection. Ruff lint/format and strict mypy pass. Initial line-length/import-order lint findings were corrected before the final check. These are decoder tests only: no employer fetches, durable inventory, scheduler, closure reconciliation or isolated fetcher behavior has been validated yet. Link validation is not a substitute for connection-time DNS/proxy isolation. Next implement company/source persistence and bounded collection epochs with conservative omission handling, then integrate the isolated fetcher and portal. Full goal remains active.

### Durable inventory implementation checkpoint

Added company/source/job/revision/association models and collection epochs, page checkpoints and observations. Reviewed the generated migration: it only creates the intended inventory tables/indexes and does not modify Procrastinate-owned tables. Added source scheduling with one catch-up after downtime, interval jitter, pause/cooldown checks and joined in-progress checks. Collection finalization validates source versions, preserves partial observations, rejects duplicate pagination as incomplete and counts omissions only after complete authoritative traversal; three complete omissions are required per source and all source associations must be unavailable before a job closes.

Worker integration is under validation. Fetch transport deliberately reports fetcher_unavailable until the planned isolated service is implemented; no direct-HTTP shortcut or network change was introduced. Initial formatting/type checks found line-length/import issues and a SQLAlchemy get() boolean-inference mismatch; corrected before ongoing tests. No milestone completion claim yet.

### Durable inventory and scheduler validated locally

Added persistent company/source watches, job identities/revisions, per-source associations, collection epochs, observations and idempotent page checkpoints. Collection operations now run on the fetch queue; the periodic scheduler joins existing work, catches up once after downtime, respects pause/cooldown and advances the regular schedule independently of retries. Page finalization is atomic with operation completion and checks the worker lease, source revision and epoch age. Cross-source merges require identical canonical job URLs within one company. Positive observations reopen jobs; closure requires three complete authoritative omissions for every known source. Non-authoritative, partial, failed and unstable-pagination runs cannot infer closure. New revisions create assessment intents when an approved profile exists; the matching handler remains a later milestone.

Validation: the complete backend suite passed 69 tests in 36.48s before the final stale-source failure guard; the final eight inventory tests passed in 2.77s afterward. Coverage includes restart between pages, replay without duplicate omissions, meaningful revisions, cross-source identity/closure, expired epochs, concurrent schedulers, source changes, failed-fetch visibility, worker redelivery, lost leases and persisted Retry-After. Ruff lint/format and strict mypy pass; Alembic consistency reports no new upgrade operations. Existing upstream test-client deprecation warning remains. No external fetching or inference occurred.

Remaining milestone 3 work: company/source and all-jobs APIs/UI, configured isolated fetch transport and integrated scheduler/browser journeys. The fetch runner currently returns a visible fetcher_unavailable block because that service has not been implemented; this is unfinished development, not an environment blocker requiring user action. Generic discovery, broad matching, ntfy, production networking/build/ingress, backup/restore and live acceptance remain open. The full goal stays active.

### Company and inventory API checkpoint

Added authenticated company create/list/edit, explicit owner-confirmed ATS sources, source interval/enable edits, bounded run history, joined manual check/discovery intents, and unfiltered cursor-paginated job/detail endpoints. Company creation persists an unresolved watch atomically with discovery intent and supports idempotency; edits use If-Match and pausing invalidates source revisions. Manual checks fan out atomically after worker lease validation. All-jobs includes unassessed functions with explicit availability and simple full-text search; shortlist requests report matching_unavailable until the matching milestone is implemented.

Initial four API regressions: three passed, pagination assertion failed with KeyError: items because its test mixed URL query parameters and HTTPX params; inspection showed params replaces the URL query instead of merging it. Corrected requests to retain the intended filters. Also removed an unused Source import found by Ruff. Revalidation is running; no completion claim. Discovery and fetch services remain unfinished, and this is not an end-to-end monitoring acceptance result.

API validation checkpoint: the complete backend suite passed 74 tests (32.69s), and TypeScript/Vite build passed with regenerated OpenAPI contracts. Confirmed the HTTPX query replacement behavior with an offline Request construction. Final review found an idempotency edge case where a pending check on another company could bypass validation of a reused explicit key; corrected keyed requests to retain their stable operation result while unkeyed clicks join pending work. Added a fifth targeted API regression; final checks are running. No live fetching or provider requests occurred.

Final inventory API checks: all five targeted API regressions passed (2.70s), Ruff and strict mypy pass. The full 74-test run preceded the final key guard; the targeted run covers that correction. Generated client production build passed. Next implement Companies and All jobs portal flows with browser validation, then isolated fetch transport and discovery. Remaining matching, ntfy and release/deployment gates stay in scope; no new environment blocker.

### Inventory portal checkpoint

Replaced preview Companies/Jobs routes with watch creation/detail/edit, manual actions, source controls/history, explicit Shortlist/All jobs views, URL filters, paginated inventory and job detail/provenance. Added a synthetic real-browser company/source/all-jobs journey; validation is in progress. Initial build failed on optional generated posting locations/publication fields; handled missing values and the subsequent build passed. Build now warns that the main bundle exceeds 500 KB minified (155.21 KB gzipped); route splitting remains a polish task. ESLint reported mixed component/helper exports, now separated. One auth regression expected a single alert but the new Jobs page can independently report an API failure; scoped the assertion to the sign-out error. Eleven other component tests passed in that initial run. No browser result claimed yet.

Inventory portal browser checkpoint: the real API/database journey passed (4.7s; 9.3s total), including watch creation, source confirmation, repeated pause/resume saves, unassessed legal/strategy inventory, text search, detail and retained company/query filters. At 375/1440 widths no overflow or axe violations occurred on company/detail states. Desktop company screenshot review exposed cramped form spacing and checkbox labels; improved spacing and 44px label targets. Also corrected source editor revision handling: untouched forms use the current source revision after company pause/resume, while edited forms retain their captured base. Extended the browser journey to save a source after pause/resume; revalidation follows. No live fetching or inference occurred.

Inventory portal follow-up: extended real-browser journey passed in 11.9s (20.3s with startup), including a source interval save after company pause/resume. Source controls now preserve dirty values/revision but use refreshed source state when untouched. Form spacing and checkbox targets were improved after desktop screenshot review. Query errors no longer steal focus from navigation or ongoing editing; form mutation errors still focus their summary. Final TypeScript/Vite build and lint pass (155.37 KB gzipped JS, 4.28 KB CSS), with the existing >500 KB minified chunk warning retained. Navigation browser regression across 375/768/1440 is running. No live fetching or inference occurred.

Remaining UI scope includes company counts/coverage summaries, richer company-level job views, feedback once matching exists, scroll restoration/new-results handling and bundle splitting. Isolated fetching/discovery, matching, ntfy and deployment/live acceptance remain unfinished. These screens are not a claim that company monitoring is end-to-end ready.

Navigation suite initially failed at all three widths because the renamed Jobs heading locator also matched Filter jobs (Playwright strict mode violation). Restricted it to the exact page heading; isolated rerun follows. This was a locator ambiguity, not evidence of failed focus behavior.

### Companies and job browsing portal validated

Final navigation suite passed all three 375/768/1440 journeys (5.4s), checking authentication/navigation focus, overflow and axe accessibility. Inspected the mobile Jobs screenshot. The extended real API/database company/source/all-jobs/detail journey passed previously in 20.3s total, with 375/1440 accessibility checks. Twelve component regressions passed before the last source-editor/focus refinements; those refinements have browser coverage. TypeScript/Vite build, lint and formatting pass; no dependencies were installed. The new synthetic seed script is restricted to the fixed disposable browser database. No private CV or live provider/source requests were used.

The design search returned generic marketing layouts even after a narrower query; retained the established UI_UX.md workspace design rather than adopting those patterns. Remaining polish/product scope stays recorded above. Next work should prioritize completing isolated fetching/discovery and the remaining inventory interactions, then matching/digests/deployment, not treating these UI journeys as final product acceptance.

### Isolated HTTP fetcher checkpoint

Added a separate fetcher ASGI entry point and worker RPC transport. The fetcher imports no application DB/profile services, accepts bounded public URL/conditional-header requests behind an independent token, requires its configured proxy, and refuses fetching until isolation_verified is explicitly enabled after deployment ACL validation. HTTP logic checks DNS answers and every redirect, strips redirect cookies/validators, bounds raw and decompressed content, enforces a 30-second overall timeout and robots policy, and keeps a small private SQLite origin-pacing/cooldown ledger across restarts. SQLite stores only origin timing; it is not an application database or queue replacement.

Initial synthetic fetcher plus inventory suite passed 16 tests (2.81s), including redirect/cookie boundaries, robots denial, decompression caps, credential/input checks, default-disabled isolation, persistent pacing and worker error propagation. Static formatting found long SQL strings/imports; corrected, with additional DNS/proxy-factory/robots-outage tests now pending. No actual public fetch, image pull or container-isolation validation occurred. Docker proxy/browser packaging, network enforcement and live collection remain unfinished.

### Isolated HTTP transport validated with synthetic responses

The complete backend suite passed 86 tests (35.29s). After correcting long Retry-After handling, all twelve fetcher tests passed (2.62s); Ruff lint/format and strict mypy pass. The fetcher ledger retains long origin backoff while internal worker retries are bounded to 30 days, so a later worker attempt still cannot bypass the origin hold. Coverage includes mixed public/private DNS rejection, proxy-only factory settings, redirect revalidation without cookies/credentials, bounded gzip/identity data, robots denial/outage/crawl-delay, service authentication/input limits, default-disabled isolation and RPC error handling. Existing upstream test-client deprecation warning remains.

No network fetch, image pull or new dependency installation ran. Proxy/browser images, Compose wiring, service secret provisioning, container bypass/rebinding/redirect tests, generic extraction and live source coverage remain unimplemented/unverified. Next continue those integration pieces and discovery; there is no new environment blocker. Full goal remains active, including matching, notifications and all release gates.

### Fetch deployment configuration checkpoint

The first public `docker pull ubuntu/squid:latest` succeeded; resolved image digest is sha256:6a097f68bae708cedbabd6188d68c7e2e7a38cedd05a176e1cc0ba29e3bbe029. Network-disabled image inspection reported Squid 6.13. This is stronger evidence than mutable online tag metadata, and the proposed overlay pins that digest. Added proxy ACLs and validated syntax via a network-none container; removed Via suppression after Squid warned that HTTP requires Via. No runtime isolation claim yet.

Added gated worker/fetcher/proxy Compose overlay and an allowlisted Docker build context excluding real CVs/secrets. First merged Compose validation failed: cannot extend service "queue-bootstrap" in compose.fetch.yaml: service "api" not found. Corrected cross-file extends to name compose.yaml explicitly; revalidation follows. This was configuration syntax, not a dependency pull failure. Base deployment/image builds, browser fetching and normal bridge isolation remain unverified.

### User-supplied CV format recheck

Ran the bounded local check against the supplied ignored PDF: one page with text, 3,847 extracted characters, no persisted extracted content and zero AI requests. Git-ignore verification passed. The example remains a local smoke test, not a hardcoded layout or committed fixture. Reading order and semantic profile accuracy remain unverified; image-only CVs still require a text-based replacement because OCR is not supported.

Selected synthetic PDF/DOCX regressions passed: 3 tests, 11 deselected (2.80s), including multi-page PDF and DOCX body/table/nested/merged-cell handling. Existing upstream Starlette/httpx deprecation warning remains. Initial invocation used backend/tests/test_profiles.py, but the wrapper runs inside backend; pytest exited 4 with "ERROR: file or directory not found: backend/tests/test_profiles.py". Corrected to tests/test_profiles.py and reran successfully. Initial sandbox inspection also failed with "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted" (exit 1); approved elevated local checks succeeded. No dependency fetch, external provider call or application code change was needed. Broader implementation and deployment gates remain open.

### Proxy ACL runtime correction

The disposable network-none Squid runtime exposed two rule mistakes: the initial IPv6 complement rule allowed ::1 to reach connection attempt (503 ERR_CONNECT_FAIL 111); explicit IPv6 ranges blocked it but also denied public IPv4 (403 ERR_ACCESS_DENIED). Added an IPv4 allow after shared method/port/private denials and before IPv6 ranges. Squid rewrites 0.0.0.0/0 to all (SECURITY NOTICE); replaced that form with two explicit /1 ranges. Final 20-case runtime matrix passed: private IPv4/IPv6/mapped loopback, private CONNECT, nonstandard ports and POST denied; public IPv4/IPv6 and HTTPS CONNECT pass ACLs then fail with ERR_CONNECT_FAIL because the container has no network. Merged Compose syntax passes. No host networking or routes were changed. Added a repeatable cached-image-only check; broader bypass, rebinding and deployment tests remain unverified and fetching remains gated off.

### Generic structured-page extraction checkpoint

Implemented offline, bounded JobPosting JSON-LD candidates with graph/list traversal, employer references, provenance, remote/location metadata, date uncertainty, expiry evidence and safe page links. Candidate extraction never asserts employer verification or authoritative coverage. Initial tests: 10 failed, 2 passed (2.64s); the shared synthetic fixture embedded an unescaped closing script tag inside a JSON description, which correctly terminated the HTML script element and made the JSON invalid. Corrected fixture serialization to escape less-than characters. Initial mypy complaint about BeautifulSoup attribute default typing was corrected. Revalidation follows; no live collection or discovery claim yet.

### Proxy configuration and generic parser validated locally

The full backend suite passed 99 tests (37.57s), including 12 generic-parser cases; Ruff lint/format and strict mypy (42 source files) pass. Existing upstream Starlette/httpx deprecation warning remains. The reusable cached-image proxy check passed 20 cases and cleaned up; the earlier manual proxy container was also removed. No live source, Brave, OpenRouter or private CV inference requests occurred. No frontend code changed or frontend/browser tests ran.

Saving the generic parser and explicitly incomplete deployment scaffolding as a local phase checkpoint. The Compose syntax and proxy ACL results do not validate image builds, private ingress, DNS rebinding or browser isolation. Next: durable company discovery with verified official-site/ATS associations and bounded continuation, generic-source persistence and browser/AI fallback; then matching, ntfy and the remaining deployment/live gates. The original full goal remains active, and no new environment dependency blocker was encountered.

### Persistent discovery checkpoint

Previous parser/proxy phase is local commit ccc34b5. Added a discovery epoch table and one-page durable operations, official-site careers traversal, exact-host ATS detection/response verification, daily unresolved/weekly resolved scheduling, and source deduplication that preserves owner-disabled sources. Page frontiers are bounded to 20 requests and saved after each lease-checked step; company revisions and epoch expiry prevent stale publication. Generic structured jobs remain explicit candidates pending generic collection integration. Name-only watches visibly report search_discovery_pending rather than pretending search ran; Brave/search implementation remains next work.

Ruff and strict mypy pass for the initial implementation. Synthetic database regressions are running for restart/replay, valid empty boards, invalid ATS replies, denied pages, changed companies, lost leases, unknown redirects and page caps. No live fetch/search/provider calls or dependency operations were made. Milestone 4 remains incomplete.

Persistent discovery targeted validation: twelve discovery tests plus five existing company/inventory API tests passed (17 total, 7.44s); Ruff and strict mypy pass. Added authenticated discovery history and recovery for a dispatcher-exhausted page operation, so an interrupted step cannot remain joined forever without being recorded. API type regeneration and production frontend build are running alongside the independent full backend regression suite. No browser journey or live discovery is claimed.

### Persistent official-URL discovery validated locally

Full backend suite passed 111 tests (42.48s); migration consistency reported no new upgrade operations. Generated API types and TypeScript/Vite build pass, with the existing 514 KB minified chunk warning. Final review identified potential lock inversion if source scheduling retained source locks while discovery acquired company locks; separated their transactions. All thirteen discovery regressions then passed (2.08s), including a separate collector connection acquiring company/source locks during the scheduling boundary. Ruff lint/format and strict mypy pass. No live fetching, search, model calls or browser UI changes were validated in this phase.

Saving the persistent official-URL/ATS discovery phase locally. Next implement Brave search with durable request budgets and ambiguity handling, generic source collection/pagination and browser/AI fallback, and display discovery evidence/coverage in the portal. Named-employer acceptance, matching, digests and production deployment/live gates remain part of the active full goal. No new dependency or environment blocker occurred.

### Brave search implementation checkpoint

Prior discovery phase is commit 5aa2a15. Added the fixed Brave Web Search endpoint with a separate default-mock search mode, mounted key setting, durable per-epoch request slots/results, 300/day and configurable 1,000/calendar-month default budgets, and persisted rate-limit cooldown. Reservations count unknown/failed attempts conservatively and cannot be silently replayed. Search receives company-name queries only; private/duplicate result URLs are excluded and snippets are not promoted to jobs or verified identity. Name-only watches and exhausted unresolved website discovery now queue a search step; ambiguous leads remain review candidates.

Initial static checks found a long test fixture line and an optional SQLAlchemy get result assigned to a non-optional variable; corrected. Synthetic provider/database tests are running. No real Brave/OpenRouter requests, key contents, private CV data or dependency fetches were used. Candidate confirmation and portal evidence are still being implemented.

### Search candidate review checkpoint

Twenty-three search/discovery regressions passed (7.04s), covering fixed endpoint and safe leads, durable replay, concurrent budget admission, monthly holds, timeouts, provider cooldown, missing credentials/mock mode and malformed/redirected responses. Added revision-checked explicit owner confirmation, queued rediscovery of the chosen company page, and a portal history/review form with inspectable links, required confirmation and conflict-preserved selection. Company editor now refreshes pristine fields after confirmation while preserving dirty edits. The targeted UI skill search returned relevant confirmation/submit-feedback guidance; retained the established visual design.

Initial TypeScript/Vite build and lint passed (156.69 KB gzipped JS; existing chunk warning). New component/browser regressions and full backend validation are underway. No live search key has been used.

UI validation checkpoint: fourteen component tests passed (7.34s), lint and formatting passed. TypeScript build failed because the new DiscoveryHistory test company omitted required interval_hours/paused fields (TS2739 at tests/discovery.test.tsx:51 and :83). Added those synthetic fixture fields; revalidation follows. This is a test fixture typing correction, not a dependency/environment blocker.

Search/review validation: full backend suite passed 123 tests (40.19s); migration consistency, Ruff lint/format and strict mypy passed. Fourteen frontend component tests pass; TypeScript/Vite build passes after fixture correction, with the existing chunk warning (156.69 KB gzipped JS). Real API/database/browser candidate journey passed in 3.9s (11.2s including startup): explicit choice/confirmation, persisted website, queued rediscovery, reload and no selection of stale candidates. At 375/1440 widths, no horizontal overflow or axe violations; mobile screenshot inspected. The browser uses a restricted synthetic seed in jobfinder_test_browser and forcibly mocks search. Existing company edit/source journey is being rerun for the pristine/dirty editor change. No live provider/source acceptance is claimed.

### Budgeted search and company review validated

The existing company watch/source/all-jobs browser regression passed (12.0s; 22.2s total), including repeated company pause/resume and source edits after the editor refresh change. The new candidate-confirmation browser journey, 123 backend tests, fourteen component tests, migration consistency and static/build checks are recorded above and in VALIDATION.md. Browser fixture services exited; no dependency installation or live source/provider request occurred.

Saving this phase locally. Next complete generic candidate verification/collection and bounded pagination, browser/AI extraction fallback, then matching, ntfy and deployment/live acceptance. Search is default-mock and Docker credential/fixed-provider egress provisioning remains unfinished. Name-only discovery now produces reviewable candidates when its configured provider is enabled; this is not a claim that all named employers or no-careers-page jobs are fully supported. The original goal remains active, with no new environment blocker.

### Generic collection integration checkpoint

Prior search/review phase is commit 2b4621e. Connected structured generic job pages to source discovery and the collection worker. Registration requires matching structured employer name or official employer URL; unverified and expired candidates are withheld. Generic sources are explicitly non-authoritative, with company identity captured in their source configuration. Collection preserves existing records on missing jobs, bad content types, unknown redirects or failures; job descriptions still enter the shared immutable revision flow. Initial targeted regressions are running. Pagination, generic AI/browser fallback and wider named-employer coverage remain unfinished; no live requests were made.

Generic integration follow-up: eighteen targeted generic/discovery tests passed (6.12s). Initial strict typing detected reuse of an evidence-dict loop variable for PageLink objects; renamed it. Added persisted generic page frontiers capped at 200, next/detail link traversal restricted to the watched site, and baseline finalization after a generic epoch with positive observations even when coverage remains partial. This prevents newly observed roles from being labelled baseline indefinitely on non-exhaustive sites. Validation of continuation/replay and baseline behavior follows.

Generic pagination checks: 26 generic/discovery/inventory tests passed (5.72s), then six targeted generic tests passed (2.71s) after adding persisted-frontier/replay and partial-baseline regression coverage. Source API now exposes authoritative coverage; the portal labels generic sources as Website sources with partial-site coverage and distinguishes saved sources from unverified candidates. Generated API contracts, frontend build and lint pass (156.79 KB gzipped JS; existing chunk warning). Full backend validation is in progress.

### Generic structured collection validated locally

The full backend suite passed 129 tests (56.75s). After the final duplicate-card guard, sixteen generic/inventory tests passed (6.22s), including bounded links, saved continuation, replay, first-observed baseline, later unrelated-function jobs, immutable revisions and omission safety. Generic pages do not refetch links already represented by accepted postings; repeated records in one epoch preserve the first accepted revision and flag unstable pagination rather than oscillating between card/detail content. Migration consistency, Ruff lint/format and strict mypy pass. Generated API/frontend build and lint passed before this final backend-only guard.

The earlier mypy failure was `Incompatible types in assignment (expression has type PageLink, variable has type dict[str, Any])` plus four associated attribute errors in discovery.py; the final renamed-loop-variable check passes. No dependencies or images were fetched, no live source/provider calls occurred, and no new browser journey was run for the static source/status labels. Saving this phase locally. Next: unstructured extraction/browser transport, conditional snapshots and source-specific coverage, followed by matching, notifications and remaining deployment/live acceptance. The full goal is active; no new environment blocker.
