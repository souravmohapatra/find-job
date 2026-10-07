# Progress and continuation

Historical private-registry endpoints in this document are anonymized as `packages.example.invalid`; this is not a working package source.

Updated: 2026-10-07.

## Current state

Implementation is active. Backend dependencies and the host-network development PostgreSQL setup are ready. Authentication and profile ingestion/review now work through the real API/database/worker; the frontend includes a generic profile editor and explicit domain-diversification choices. Tests use synthetic data and mock inference. OpenRouter task configuration and provider handling now have mocked transport and local browser validation. Live provider acceptance, richer synthetic profile fixtures, company collection, matching, notifications and deployment gates remain to be completed. Normal Docker bridge networking is still a deployment-server validation requirement.

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
