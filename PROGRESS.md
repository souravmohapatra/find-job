# Progress and continuation

Historical private-registry endpoints in this document are anonymized as `packages.example.invalid`; this is not a working package source.

Updated: 2026-10-07.

## Current state

Implementation is authorized and in progress. Backend dependencies are installed and locked through the approved package-registry Python index. Backend authentication/migration tests now pass using the explicitly authorized development-only host-network PostgreSQL override. Normal Docker bridge networking remains unverified on this host and must be validated on the deployment server. The frontend authentication/navigation slice has passed mocked validation; the integrated foundation milestone and remaining product flows are still pending.

## Host-network development alternative — 2026-10-07 (verified)

The user authorized a development-only PostgreSQL host-network alternative, with PostgreSQL explicitly restricted to 127.0.0.1:55439. Added compose.test.host.yaml as an opt-in override of the disposable test database, removing port mappings and setting both server and health-check ports explicitly. Normal compose.yaml deployment architecture is unchanged.

Verified the merged configuration specifies host networking, no port mappings/networks, and the exact PostgreSQL listen address/port. Stopped the old disposable bridge test container to release the port, then ran:

```sh
docker compose -f compose.test.yaml -f compose.test.host.yaml up -d --wait --pull never db
```

The service became healthy from the cached PostgreSQL image. `ss -ltn 'sport = :55439'` showed only `127.0.0.1:55439`; Docker inspection returned network mode `host`. An authenticated host psycopg connection succeeded using the unchanged test endpoint. SQL verified listen_addresses=127.0.0.1, port=55439, server address=127.0.0.1 and current database=jobfinder_test. The first address assertion failed because PostgreSQL rendered the inet value as `127.0.0.1/32`; using `host(inet_server_addr())` normalized it and the corrected assertion passed. This was a verification-format issue, not a connection failure.

`python3 scripts/test-backend.py -q` completed with **7 passed in 1.33s**, covering initial migration, private routes, owner creation protection, login/session/logout, CSRF/origin checks, session rotation/expiry, durable throttling and production security settings. The existing FastAPI/Starlette test-client integration emits an httpx deprecation warning; it did not fail the tests. Added explicit Alembic path splitting and a migration connection timeout so migration startup is bounded as well as application connections. Pinned the test database to the digest of the cached, tested image. Corrected the development secret generator to write a newline for newly created secrets; existing secrets were preserved.

Final validation after the timeout/configuration cleanup: Ruff lint/format and strict mypy passed; backend tests passed again (7 passed, one upstream test-client deprecation warning, 2.73s). The digest-pinned merged Compose configuration passed inspection. Backend authentication/migration source, tests, test Compose files and development scripts are ready for the validated foundation commit; production Compose/image scaffolding remains outside that validated slice.

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
