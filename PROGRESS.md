# Progress and continuation

Historical private-registry endpoints in this document are anonymized as `packages.example.invalid`; this is not a working package source.

Updated: 2026-10-09. Local live API validation canceled by the owner; continuation moves to the deployment host.

## Deployment-host execution checkpoint — 2026-10-09

Owner assigned execution on this host (x86_64, Ubuntu 24.04.3, Python 3.12.3, Node v24.11.0, npm 11.11.1, Docker 29.1.5, Compose v5.0.1, Docker context `default`, GPG 2.4.4). `uv` is not installed; the old pin is 0.12.23. Free disk on `/` is about 18 GB and RAM is about 15 GB. Unrelated Docker containers and ports (for example ntfy on 127.0.0.1:8093, beng-tasker on 8000) exist; they will not be touched.

Intake findings: `backend/uv.lock` (390 `resolved` entries) and `frontend/package-lock.json` point at the private artifact registry host. `deploy/.env`, `.secrets/` and `backend/.venv` do not exist. `.env` (ignored) defines `OPENROUTER_KEY` and `BRAVE_API_KEY`; the backend reads `JOBFINDER_OPENROUTER_KEY_FILE` instead, so the key must be provisioned as a key-only file. Values were not printed.

Route decision before any install attempt: public PyPI for backend locks and uv, and public npm registry for the frontend lock, both with TLS verification enabled. Reachability was checked with HEAD requests only: pypi.org, registry.npmjs.org and openrouter.ai returned HTTP 200; registry-1.docker.io returned 401 (reachable, unauthenticated). No certificate, proxy or registry trust change is planned. Dependency failures on these routes stop the affected setup path.

Next: provision a project-local uv 0.12.23 under ignored `.tools/`, regenerate locks for the public registries, review the diff, then frozen installs and the Docker builds.
## Live-validation ledger checkpoint — 2026-10-09

Added `backend/app/ai/run_ledger.py`: a persistent cumulative admission ledger (60 requests / US$1, whichever first). It reserves each call's bound before dispatch, holds unresolved cost, and survives process restarts. Added `backend/tests/test_run_ledger.py` (5 tests: request cap, held-spend cap, unknown-cost persistence across restart, known-cost release, invalid-cost rejection). Ran them through `scripts/test-backend.py` against the disposable test database: 5 passed, exit 0. No inference request, key read, or paid call occurred.

Not yet done: wiring the ledger into `provider.infer`; the Phase A launcher with the temporary owner-only key-file bridge; Phase B offline harness; Luna/Jev contract checks. The ledger is not yet enforced on any live path. Next action: wire admission into the infer path with offline tests, then build the launcher, then proceed to the Phase A Gate.

## Ledger wiring checkpoint — 2026-10-09

Committed `24f638b` (ledger slice), then wired the ledger into the live dispatch path (local commit pending at write time): `provider.infer` now admits each call to `RunLedger` after the database reservation and before the HTTP POST; `BudgetRefused` finishes the call as a known-free rejection (`ai_budget_<reason>`, no request sent) and raises `ai_budget`. Settlement mirrors every `finish` outcome; transport and unreadable-response failures keep the bound held. `settle` is idempotent (the success path finishes one call twice). New `Settings.live_ledger_path` (default `.data/live_run_ledger.json` under the ignored `.data/` directory); active only when `JOBFINDER_INTEGRATION_MODE=live`, so mock mode is untouched.

Checks: `ruff check`, `ruff format --check` and strict `mypy` pass on all touched files. New tests: cumulative-cap refusal issues no HTTP request and records a free failed call; live calls settle the ledger (`known_usd 0.001`, nothing held); transport failure keeps cost held. Full backend suite: 296 passed, exit 0, against the disposable test DB via `scripts/test-backend.py`. No live request, key read or spend occurred.

Blocker decisions confirmed by the owner: (1) I may create the temporary key bridge `.secrets/openrouter_api_key` (0700 dir / 0600 file, exclusive creation) from `.env`, pointing `JOBFINDER_OPENROUTER_KEY_FILE` at it for the validation run only, deleting it on orderly shutdown; (2) Luna proceeds first, Jev's `provider.data_collection=deny` enforcement is verified live before Jev is validated; (3) Node v24.11.0 drift from the plan's Node 22 is accepted (frontend tests and build already pass on it).

Next: build the Phase A launcher (offline harness, temporary key bridge, `--execute-live` gate), then the Phase A gate checks.

## Phase A launcher checkpoint — 2026-10-09

Added `scripts/validate-live-api.py`, the development-only Phase A launcher (offline by default; `--execute-live` gates live-mode preparation). Default run: verifies `.env`/`.data`/`.secrets` are git-ignored (metadata only), parses `OPENROUTER_KEY` from `.env` with a line parser (no interpolation, no shell, value never printed), reconciles the persistent run ledger, demonstrates the Gate A refusals (request cap, in-flight spend cap, persistence across restart — on per-run throwaway ledgers, removed after), verifies the test Postgres listener is loopback-only on 127.0.0.1:55439, provisions a dedicated `jobfinder_test_live_api_<run-id>` database in the compose.test.yaml container (idempotent for reruns), applies migrations + queue schema + synthetic owner via the existing alembic/`bootstrap_queue`/`create_owner` helpers, caps the app's daily AI limits to the remaining cumulative allowance, and verifies process settings (development, live AI, mocked search/notifications, no mock fixtures, no fetcher URL). Run metadata is saved under ignored `.data/` with no secrets.

`--execute-live` additionally creates this run's temporary key bridge under `.secrets/live-api-<run-id>/` (dir 0700, file 0600, exclusive creation) before the first application import — required because the settings singleton caches paths at first use — verifies key availability through `provider.key_available()`, performs one authenticated metadata GET of the key's spending backstop (tracked separately in run metadata), and removes only this run's bridge on orderly shutdown (verified: no leftovers, including on failure paths).

Observed: dry-run exit 0; same-run-id rerun exit 0 (idempotent); `--execute-live` exit 0 with key backstop `usage=0, limit=5` (provider-side $5 backstop, consistent with zero spend). Key value, database URL never printed. No billable request: inference attempts 0, known spend US$0, held US$0; metadata attempts 1. `ruff check` and `ruff format --check` pass on the script.

Gate A status: the offline-refusal, disposable-state, process-settings and persistence criteria are demonstrated by the launcher runs above. Not yet claimed: Gate A sign-off awaits the Phase B mocked-transport coverage and the Phase C probe step per the plan ordering.

Next: Phase B — implement the Jev Decisions adapter at the task boundary with deterministic MockTransport coverage for both adapters per the Phase B table, then Phase C live probes.

## Phase B decisions adapter checkpoint — 2026-10-09

Implemented the adapter split at the task boundary:

- `backend/app/ai/decisions.py`: the Decisions wire protocol (typed choice/noul/score questions and answers), parsed fail-closed. Booleans and non-finite values are rejected before pydantic can coerce `True` to `1.0` (verified coercion happens in lax mode). `normalize` checks answer/question type match, missing and extra answer keys, unknown choice values, exact probability-key sets, range checks and the documented `PROBABILITY_TOLERANCE` (0.02) on probability sums; bad probabilities are never renormalized. Missing usage cost is unknown, never zero.
- `TaskConfig.protocol: Literal["chat", "decisions"] = "chat"`: revisions saved before this field keep their historical chat meaning through the default. Save-time guard (422 via `problem`) and dispatch-time guard restrict `decisions` to `job_matching`.
- `provider.dispatch_decisions`: single-attempt dispatch to the absolute URL `https://openrouter.ai/api/alpha/decisions` (joining `alpha/decisions` onto the `/api/v1/` base would target the wrong endpoint — flagged in the plan and asserted in tests). Sends only documented Decisions fields (`data_collection=deny`, `zdr`, `allow_fallbacks`, `max_price`); chat-only `require_parameters`/endpoint `only` tags are not blindly sent. Shares `reserve`, `estimate_bound`, the run-ledger admission gate, `finish` and settlement with the chat path. Typed-contract errors, unknown returned models and transport failures are terminal: no chat repair re-send, paid attempt retained, missing cost stays held. The returned dated version form (`typesafe/jev-1.13-20260917`) is accepted by an exact-prefix digit-suffix rule only; no broad prefix acceptance.
- Chat path defect fixed per the Phase B row "model mismatch is not a repairable syntax error": an unrequested returned model now terminates with `ai_model_mismatch` instead of consuming a repair re-send. No test had pinned the old behavior.
- `matching.decisions_adapter` (small adapter): typed questions for primary function (choice over job spans with `insufficient`), relation, a 4-band relevance score, plausible connection (noul), and per-criterion outcome plus supporting-span questions with explicit insufficient options. The interpreter cites exact span texts from state only (no model-generated quotes), fails closed when a known outcome lacks selected support, and maps insufficient evidence to `unclear`/`None`/`unknown`. `validate_task` dispatches a decisions probe (typed "ok" question) for decisions-protocol revisions; `reconcile_call` now releases the run-ledger hold when provider billing is confirmed.

Checks: full backend suite 306 passed, exit 0, against the disposable test DB (10 new Phase B tests: probe contract/versioned-model/ledger settlement, six terminal typed-contract scenarios with no repair re-sends, unknown-model billing retention, missing-cost hold, transport-failure no-duplicate, 429 cooldown, adapter interpretation incl. insufficient path and unsupported preference outcome, chat mismatch terminality, protocol save restriction). `ruff check`, `ruff format --check`, strict `mypy` pass on all touched files. No live request: inference attempts 0, spend US$0, held US$0 (all HTTP is MockTransport).

Gate B status: mocked tests pass for both transports and the shared budget/state logic; the small matching adapter and probe dispatch exist; production code is not bypassed. Not claimed: prompt-quality (Phase D/E) and live behaviour (Phase C).

Next: Phase C — bounded live connectivity and schema checks through the launcher (at most 6 successful probes, up to 4 further attempts for diagnosis, inside the cumulative 60/US$1 cap), including the Jev `data_collection=deny` enforcement probe.

Advisory review fix (same day): an advisor-model review correctly flagged that `dispatch_decisions` returned the adapter's `interpret` result without running the domain `validate`/`category` enforcement the chat path applies — production Decisions matching would have bypassed evidence validation, and the unit tests masked it by calling `validate` manually. Fixed inside `matching.decisions_adapter.interpret`: it now runs the same `validate(result, preferences, spans)` and `category(result, preferences)` before returning, so a Decisions outcome that fails domain validation terminates with `ai_schema`, retains the paid attempt, and never marks the call succeeded. Added the recommended end-to-end MockTransport test: `assess` over a decisions revision whose answer selects `job:title` instead of the required `job:description` is rejected with billing retained. Full suite: 307 passed, exit 0; ruff and strict mypy clean.

Advisor-review hardening batch (same day, from the full advisor findings; commit pending at write time):

- Blocker (Decisions billing bound): the Decisions protocol has no provider-side output-token field, so no request-level bound exists. `dispatch_decisions` now reserves the entire remaining allowance — this prevents multi-call under-counting but does NOT bound a single response's charge — and live Decisions dispatch is disabled by default via `Settings.decisions_live_enabled=False` (`ai_decisions_blocked`). Enabling it requires an owner decision on a demonstrated per-request bound or a provider-side key limit at or below the approved US$1 ceiling (the observed US$5 key backstop exceeds the ceiling; lowering it is a dashboard action for the owner, not an API call). Comment and PROGRESS state the reservation's limits honestly.
- Backstop check (launcher): now requires a positive numeric provider-side `limit` and usable `usage`; an unset or unusable limit blocks live preparation; a limit above US$1 prints a warning that the owner should lower the key limit.
- Mock-mode hole: verified already covered by `provider.client()`, which refuses any real HTTP client outside live integration mode (the advisor's slice omitted that function); no change needed.
- Ledger durability: `os.replace` is followed by a directory fsync; a missing ledger file beside its `.initialized` marker (written with fsync after first initialization) raises instead of silently resetting the allowance. Initialization is race-free (under the file lock); a concurrency test proves exactly `TOTAL_REQUESTS` of `cap+10` concurrent admissions succeed.
- Launcher: `--run-id` is validated (`[a-z0-9_]+`) immediately after parsing, before any path construction; `provision_database` checks the subprocess result and distinguishes verified reuse from failure (sanitized message, original preserved in diagnostics); `build_key_bridge` removes its partial directory/file itself on any write failure.
- Matching adapter: the contract-valid `insufficient` primary-function answer now maps to an unclear, score-less assessment instead of a terminal failure; cross-answer contradictions (`unrelated` with a high band, `aligned` with the lowest band) are rejected before a succeeded state; `decisions.request_body` validates question specifications locally (type-specific criteria, nonempty sets, noul true/false) before any paid request; explicit-null confidence parses as absent metadata.
- Tests: 5 added (decisions blocked by default with zero posts; decisions cap refusal before dispatch with zero posts; concurrent admission; ledger loss detection; insufficient-duties mapping). Full suite: 311 passed, exit 0; ruff and strict mypy clean on all touched files.

Owner decision (2026-10-09): live Decisions (Jev) dispatch is unblocked only after the OpenRouter key limit is lowered to at most US$1 — a provider-enforced cap inside the approved ceiling. The owner performs this in the OpenRouter dashboard (never through the API, per project rules); the launcher's metadata check then requires `limit <= 1.0` before `decisions_live_enabled` may be set. Phase C order unchanged: Luna probes first, then the single Jev `data_collection=deny` probe. Until the lowered limit is verified, Jev stays `ai_decisions_blocked`.

Advisory fix (same day): the backstop check now requires finite usage/limit (`NaN` previously slipped through both comparisons), rejects resetting limits (`limit_reset`, e.g. `"monthly"` — a resetting allowance cannot enforce the cumulative cap), and rejects exhausted or non-finite `limit_remaining` (both documented in the OpenAPI key schema). A real diagnostics log now exists: `provision_database` failures write the sanitized psql stderr to ignored `.data/live_run_<run-id>_diagnostics.log` instead of claiming a nonexistent log. New `backend/tests/test_live_launcher.py` (9 tests, all offline via faked `httpx.get`, NaN injected as raw wire bytes): valid static limit passes; oversized/unset/NaN-limit/NaN-usage/resetting/exhausted/NaN-remaining all rejected; the metadata attempt counter increments even on failure. Full suite: 320 passed, exit 0; ruff clean. Still awaiting the owner's dashboard action (key limit ≤ US$1) before Phase C.

Owner decision revised (same day): the US$1 cap is advisory for validation only; the $5 monthly-resetting key limit is acceptable as an additional provider backstop. If any charge exceeds the cap, stop and consult the owner. The launcher reports oversized/resetting backstops as notes; only an absent, non-finite or exhausted backstop blocks. `run_probes()` (Phase C: pending-operations check, synthetic bounded revisions, Luna probe then Jev probe, stop at first failure) was exercised offline with MockTransport first — success path (two probes, exact URLs, terminal states, revisions), first-probe failure path (zero Jev posts, one revision) and a model-mismatch guard catch — before its first paid run.

## Phase C live probe checkpoint — 2026-10-09

First live OpenRouter traffic (run `20261009_142304`): Luna chat probe succeeded — returned `openai/gpt-6-luna`, cost $0.00000635, latency 6336 ms, generation ID recorded. Jev Decisions probe succeeded with `data_collection="deny"` accepted — returned `typesafe/jev-1.13-20260917` (dated-version rule), cost $0.00001369, latency 490 ms, generation ID recorded. Ledger after: 2 attempts, $0.000020042 known, nothing held. Bridge removed; no leftovers.

En route, one production defect surfaced and was fixed before any probe could run: `endpoint_tags` treated the documented `overrides` tier list (and initially its `min_prompt_tokens` thresholds) as unknown per-request charges, rejecting every Luna endpoint. Replaced with `priced_within` (base + every override tier validated against the configured ceilings; `discount`/`min_prompt_tokens` treated as metadata; uninterpretable values fail closed) plus two regression tests. Suite: 324 passed, exit 0; ruff and strict mypy clean.

Evidence recorded in VALIDATION.md. Limits: one probe per protocol, synthetic payloads; deny enforcement is verified only to the extent externally observable (request accepted, routed to TypeSafe, no error). Next: section 8 remaining items — no further live probes until the next batch; then phases 9+ of the FINISH plan (fetching isolation, browser collection, ntfy digest, backups) per plan order.

## Fetch isolation preparation checkpoint — 2026-10-09 (section 9, prepared not installed)

Mapped the existing topology: the fetcher already has token-only secrets, no DB/CV/provider credentials, no Docker socket, no host network; egress goes only through the Squid proxy (`deploy/squid.conf` denies non-global IPv4/IPv6 at connection time, ports 80/443 only); `resolve_public` pre-checks DNS and refuses non-global results; body limits, robots, pacing and cooldowns are enforced (`app/fetcher/http.py`, `governor.py`).

Prepared for owner review, nothing installed: `deploy/fetch-control-rules.sh` (install/verify/rollback/show) implements seven stateful rules in `DOCKER-USER` marked `jobfinder-fetch-control`: established/reply flow acceptance on both fetch bridges; fetcher-initiated NEW connections dropped on `fetch_control` and everywhere else (rule 7 covers cross-bridge/LAN/host/tailnet); fetcher→proxy:3128 the only accepted NEW; proxy-initiated NEW dropped. Worker→fetcher RPC intentionally falls through to Docker's own chains. The installer refuses to run unless both networks are internal and `bridge-nf-call-iptables=1` holds (same-bridge traffic reaches the rules only through that hook), verifies address freshness at verify time, and rollback removes exactly the marked rules. Persistence: `deploy/jobfinder-fetch-control.service` (oneshot after docker.service, idempotent install + verify, rollback on stop). Review document: `deploy/fetch-isolation.md` including the section 9.2 matrix plan (disposable listeners, synthetic payloads, no real metadata services/LAN targets). `bash -n` passes; `show` reports no managed rules present.

NOT done: installation (requires owner approval — host firewall), the real-container matrix run, the `JOBFINDER_FETCH_ISOLATION_VERIFIED` enablement/preflight change. Next: owner reviews the rule set; on approval, install, run `scripts/test-fetch-isolation.py` against the controlled acceptance instance, then implement the reviewed enablement override.

Advisor corrections (same day, before any install): rule 5 lacked `-p tcp` (iptables would reject it mid-install and leave a partial policy — install is now transactional with auto-rollback); `container_ip` returned one address for a dual-homed container (now per-network: the fetcher has distinct `fetch_control`/`fetch` addresses and the rules reference both); and `DOCKER-USER` is a FORWARD hook that never sees container→host traffic, so the fetcher addresses also get explicit INPUT drops (8 DOCKER-USER + 2 INPUT rules; the earlier PROGRESS claim of host coverage was wrong and is corrected here). The rule module is now sourceable (`apply_rules`/`remove_rules`, marker overridable) and the new `scripts/test-fetch-control-harness.sh` exercises the exact rule function against a disposable two-bridge topology with busybox-nc probes (worker→fetcher allowed, fetcher→worker blocked, fetcher→proxy:3128 allowed, proxy→fetcher blocked, fetcher→real-host-listener blocked via INPUT, embedded-DNS still resolving) and full cleanup on exit. It requires sudo (passwordless sudo is not available on this host); the owner runs `sudo scripts/test-fetch-control-harness.sh`, and the real install proceeds only after it passes.


## Deployment-host checkpoint - 2026-10-09 (dependency intake)

Done: uv 0.12.23 provisioned under ignored `.tools/uv-pkg` (python3-venv is not installed, so `ensurepip` venv creation failed and no sudo was used). `backend/uv.lock` regenerated against public `pypi.org` / `files.pythonhosted.org` via `uv lock --default-index https://pypi.org/simple` in a scratch copy first. Comparison: 57 packages before and after, no version changes, no adds or removes, 252 artifact hashes preserved. `uv sync --project backend --frozen --python 3.12` succeeded (exit 0).

Frontend npm lock: the earlier fetch blocker (`ENOTFOUND` on the previous package host, `@tailwindcss/oxide-wasm32-wasi@4.3.3`, 3 attempts) is resolved by owner authorization to use the public npm registry. `frontend/package-lock.json` was rewritten with a script (since removed) that changed only the 390 `resolved` URL prefixes to `https://registry.npmjs.org/`. Verified: the diff is exactly 390 `resolved` lines; 390 `integrity` values unchanged; `npm ci --ignore-scripts --registry=https://registry.npmjs.org/` in a scratch copy exited 0 (321 packages added). Frontend image, compose stack, Luna/Jev live validation and budget work are not yet started.

Frontend verified on the real checkout from the public-registry lock: `npm ci --no-audit --no-fund --registry=https://registry.npmjs.org/` exit 0 (321 packages added); `npm run build` exit 0 (Vite build, `dist/` produced). Frontend image: `docker build -f deploy/frontend.Dockerfile -t jobfinder-frontend:local .` exit 0 (image `e2c85fec1ff9`). Smoke: `caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile` printed `Valid configuration` (exit 0); `/srv/index.html` and `/srv/assets` present.

Checks run on this host (all exit 0 unless stated):
- Frontend unit tests: `npm test` (vitest) 30 of 30 passing across 11 files.
- Test DB: created only `.secrets/test_db_password` (mode 0600, owner-only `.secrets`, value never printed). `init-dev.py` and `init-deployment.py` NOT run: `init-dev.py` would create `db_password` at 0600, and `init-deployment.py` would create `deploy/.env` and empty provider/publisher secrets. Pinned `postgres:17-alpine@sha256:b0f956…` pulled by digest over the normal bridge path. Started with `compose.test.yaml` only; `compose.test.host.yaml` NOT used. Published as `127.0.0.1:55439 -> 5432`; `ss` shows listener on 127.0.0.1:55439 only; healthy.
- Backend: `ruff check` and `ruff format --check` on backend and scripts passed; strict `mypy app` passed (63 files).
- Backend tests: `python3 scripts/test-backend.py -q` 287 passed in 61s against `jobfinder_test` on the disposable DB.

Not yet run: frontend lint/format, browser (Playwright) suite, compose stack, Luna/Jev live validation, budget ledger (0 inference requests, US$0 spent to date).
Remote: read-only `git ls-remote origin` shows `refs/heads/master` at `8448f6b`; the new commits `b732d4c`, `1070d2a`, `1dba8ce`, `e68773c` are local only. Per owner decision: history unchanged; no remote writes.

History note: five earlier commits (`c3eacc7`, `00b4894`, `f8931ad`, `b732d4c`, `1dba8ce`) contain the previous package-host string in history. Removing it from history requires an explicit rewrite decision from the owner; the working tree and lock are clean.



## Current state

The owner reports that OpenRouter verification cannot be performed on this development network and has canceled the local live plan. Do not resume metadata probes, paid requests or offline implementation under that canceled assignment. Continue on the intended host using [FINISH_DEVELOPMENT_AND_VALIDATE.md](FINISH_DEVELOPMENT_AND_VALIDATE.md), section 8 and [DEPLOYMENT_API_VALIDATION.md](DEPLOYMENT_API_VALIDATION.md), when assigned there.

Preserved the other agent's previously uncommitted findings: a single unauthenticated model-endpoint metadata GET failed certificate verification (`httpx.ConnectError`, diagnostic exit 2). Recorded inference attempts: 0; known spend: US$0; held spend: US$0; metadata attempts: 1. This evidences a TLS failure, not proof of a particular network policy's causal mechanism. No key or real CV was read according to that checkpoint. No network retry was made during cleanup.

Moved the detailed plan to a deployment-only companion, preserving Luna/Jev models, medium reasoning where supported, native decision/evidence handling and the cumulative US$1 / 60-request cap. The parent guide now incorporates that phase instead of requiring the older preset implementation. Deployment tests must use normal Compose networking; the old host-network database workaround is not transferred. No application implementation or live validation has passed through this documentation cleanup.

Documentation validation passed: all nine changed/new Markdown documents have valid local links, whitespace and balanced fences; no references to the retired filename remain. Verified preservation of the medium-reasoning preference and TLS diagnostic, deployment-only networking instructions, and that the inspected remote tip is an ancestor of the local branch. Saving the cleanup in a local commit; next the owner pushes and assigns continuation on the deployment host. Existing `.env`, secrets and running development database are outside this documentation cleanup and remain untouched.

## Historical handoff and implementation context

The publication, preset and local-execution notes below are historical. Current model, environment and budget direction is above; the old preset choice and instructions to continue local launcher work are superseded.

Repository publication cleanup: employer-specific wording and internal hostnames have been removed or anonymized in current and historical Markdown snapshots. Commit messages are generic and authors/committers use the owner's personal identity. Recorded commit references in current documents have been mapped to the rewritten history. Application files and dependency lockfile contents are unchanged; private-registry lock migration remains a separate deployment prerequisite. Lockfiles remain tracked reproducibility inputs, not build artifacts. The owner must replace the already-published branch with an explicit force-with-lease push; no push was performed here.

Cleanup verification: scanned all 42 rewritten commits and 199 distinct historical Markdown versions, checked current local links and whitespace, and verified every non-Markdown file blob remained identical at its corresponding historical commit. Personal author/committer metadata and commit dates were preserved. No dependency downloads or runtime tests were needed for this documentation/history change. Recovery bundles and commit mappings were retained outside the repository; obsolete local history references are removed after validation. The next implementation action remains the deployment-host intake in FINISH_DEVELOPMENT_AND_VALIDATE.md.

Deployment handoff update: the owner has selected continuation on the deployment environment with a local LLM development agent. Read FINISH_DEVELOPMENT_AND_VALIDATE.md for the ordered remaining work and stop conditions. The owner will supply an OpenRouter key and create @preset/job-finder for application testing; current code needs preset support before that value works. Host inputs, a finite test budget, fresh builds and runtime acceptance remain pending. The earlier “no environment decision” impasse below is historical; no deployment work was executed by this documentation task.

Implementation is active; no live end-to-end completion is claimed. Profile review, company inventory/discovery, broad matching, collection selectors, notification controls and portal journeys have local synthetic/API/database/browser validation. Route splitting is saved in ccae444. Isolated ntfy server checks passed, but application-to-ntfy Compose delivery and delivery to the owner's device remain unverified. HTTP fetching remains disabled until deployment isolation is validated. Basic encrypted backup and isolated restore scripts now pass 15 recovery checks, including a disposable full data restore. Retention is implemented with synthetic validation; nightly systemd templates pass syntax/calendar checks. Timer installation/execution and deployed-application recovery acceptance remain unfinished. Following the advisory review, the next priority is basic backup/restore, then intended-host deployment and a representative real collection/matching/digest journey. Optional polish and additional capabilities are deferred; existing requirements remain in scope.

Active blocker: Python Playwright dependency setup failed through the package-registry Python proxy with `invalid peer certificate: UnknownIssuer` (uv exit 2). No retry or trust workaround was attempted; awaiting the user's trust fix or explicit new retry instructions. This blocks browser dependency setup, not independent work using installed packages. Normal Docker bridge/isolation checks still require the intended deployment environment. Full goal remains active; no end-to-end live monitoring claim is made.

## Host-network development alternative — 2026-10-07 (verified)

The user authorized a development-only PostgreSQL host-network alternative, with PostgreSQL explicitly restricted to 127.0.0.1:55439. Added compose.test.host.yaml as an opt-in override of the disposable test database, removing port mappings and setting both server and health-check ports explicitly. Normal compose.yaml deployment architecture is unchanged.

Verified the merged configuration specifies host networking, no port mappings/networks, and the exact PostgreSQL listen address/port. Stopped the old disposable bridge test container to release the port, then ran:

```sh
docker compose -f compose.test.yaml -f compose.test.host.yaml up -d --wait --pull never db
```

The service became healthy from the cached PostgreSQL image. `ss -ltn 'sport = :55439'` showed only `127.0.0.1:55439`; Docker inspection returned network mode `host`. An authenticated host psycopg connection succeeded using the unchanged test endpoint. SQL verified listen_addresses=127.0.0.1, port=55439, server address=127.0.0.1 and current database=jobfinder_test. The first address assertion failed because PostgreSQL rendered the inet value as `127.0.0.1/32`; using `host(inet_server_addr())` normalized it and the corrected assertion passed. This was a verification-format issue, not a connection failure.

`python3 scripts/test-backend.py -q` completed with **7 passed in 1.33s**, covering initial migration, private routes, owner creation protection, login/session/logout, CSRF/origin checks, session rotation/expiry, durable throttling and production security settings. The existing FastAPI/Starlette test-client integration emits an httpx deprecation warning; it did not fail the tests. Added explicit Alembic path splitting and a migration connection timeout so migration startup is bounded as well as application connections. Pinned the test database to the digest of the cached, tested image. Corrected the development secret generator to write a newline for newly created secrets; existing secrets were preserved.

Final validation after the timeout/configuration cleanup: Ruff lint/format and strict mypy passed; backend tests passed again (7 passed, one upstream test-client deprecation warning, 2.73s). The digest-pinned merged Compose configuration passed inspection. Backend authentication/migration source, tests, test Compose files and development scripts were committed as 597d98f; production Compose/image scaffolding remains outside that validated slice.

The host-network alternative is now verified for development database access and the current backend tests. It does not fix the Docker bridge, validate service-to-service networking or prove production deployment/isolation. No VPN, firewall, host routes, global certificate settings or credentials were changed. The disposable database remains running in host-network mode for further development. Re-run normal Compose networking, private ingress and fetcher isolation checks on the intended Ubuntu server before deployment. The old bridge-blocker evidence below is retained as history; backend development is no longer blocked on it.

## Previous checkpoint: Docker/database blocker — 2026-10-07

Implementation is blocked on the development host's Docker database connectivity. This entry records the actual outputs from the preceding implementation checks; no new network probe or dependency retry was run for this documentation update.

### Completed and saved

- `c3eacc7`: backend dependency manifest/lockfile and validation evidence. The authorized package-registry retry succeeded with TLS enabled and SSL_CERT_DIR unset for that process only.
- `00b4894`: frontend authentication/navigation foundation. Production build, lint, formatting, six component tests and three mocked browser journeys passed. These do not prove backend or full product behavior.
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

The user clarified that this development environment is on a restricted development network: failed dependency fetch/sync/image pulls must be reported as blockers rather than worked around. This rule is now in AGENTS.md. Await user-provided dependency/network configuration before resuming installation. The validated planning baseline is committed as 1f8d3d8; do not represent the unvalidated implementation as a completed phase.

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

Continued after validated provider commit `6f5a75a`. Added paginated original-document metadata, retention editing, confirmed original removal and explicit full-profile deletion in the UI. Deletion clears cached raw draft data and cancels unfinished ingestion; AI reservation admission now checks operation cancellation before another request. Original removal preserves draft/reviewed facts, while full purge removes them. Profile revision counters now remain monotonic across purge/recreation, preventing an old editor from accidentally reusing a new profile's revision number. Added backend and browser regressions; validation is in progress.

Data-management check results so far: 44 backend tests passed before the cancellation-admission change; the 25-test provider suite passed afterward, including the new cancellation guard. Eight frontend tests, build, lint and format checks passed. The first new browser journey failed during synthetic API setup: PATCH /api/v1/profile returned 401 because the test read session state before asynchronous sign-in completed. Updated the test to wait for the authenticated CV control. Also corrected purge success text and cancelled-draft/download visibility. Browser revalidation is pending.

### Profile storage controls validated

The final data-management browser journey passed (3.1s; 8.1s including fixture startup): authenticated retention change persisted across reload, original download became unavailable after confirmed removal while reviewed facts remained, full purge required typed confirmation, and profile/draft/document APIs returned the cleared state afterward. Checked 375/1440 widths without overflow or axe violations; desktop screenshot inspected. Fixed a real interaction issue exposed by the browser: a server-controlled retention checkbox briefly reverted while saving. It now updates immediately, waits for persistence, and rolls back on failure. A focused component test verifies rollback without clearing existing draft data.

Nine frontend tests, production TypeScript/Vite build, ESLint and formatting pass. Backend full suite passed 44 tests before the added cancellation admission guard; the 25-test AI suite then passed with that guard. Final profile regression/static checks are recorded below. Remaining milestone 2 work is full profile conflict recovery and billing-recovery UI/verified unknown-cost resolution, plus richer synthetic analysis fixtures; live acceptance still awaits chosen models/key. The main monitoring/matching/digest/deployment milestones remain unfinished. No live API or real-CV inference occurred.

Final profile regression run: 13 tests passed (4.42s), including retention/cancellation and purge/recreate conflicts. Final Ruff lint/format and strict mypy pass. Frontend fixture ports 8000/5173 are no longer listening after teardown. The original dependency/network boundaries remain unchanged.

### Profile conflict recovery checkpoint

Continued after storage-controls commit `0519352`. Added an explicit comparison workflow that preserves the editor's original revision across background refreshes, presents local/saved-profile/saved-draft field choices, and requires renewed review before saving. The new draft reconciliation endpoint checks both current profile revision and draft version under the profile lock, validates evidence and does not activate the draft. Copied approved-profile facts are treated as owner-confirmed corrections when the source CV differs. Fourteen profile backend tests, ten frontend tests, strict mypy, Ruff, TypeScript/Vite build and ESLint pass so far. Real-browser and additional draft-provenance checks are in progress; no completion claim yet.

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

Billing recovery saved as local commit `8e3559f`. Started milestone 3 with transport-independent Greenhouse, Lever and Ashby request/normalization contracts, checked against the official public API documentation. Source metadata includes full plain-text descriptions, canonical links, locations, published dates where supplied, workplace/employment labels and salary data. Collection has no profile dependency or match filtering. Lever handles global/EU hosts and explicit continuation offsets; duplicate/invalid postings or unverifiable counts prevent complete-inventory claims. Ashby excludes explicitly unlisted posts. Tracking parameters are removed conservatively while meaningful job parameters remain.

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

Previous parser/proxy phase is local commit 3dcb9ce. Added a discovery epoch table and one-page durable operations, official-site careers traversal, exact-host ATS detection/response verification, daily unresolved/weekly resolved scheduling, and source deduplication that preserves owner-disabled sources. Page frontiers are bounded to 20 requests and saved after each lease-checked step; company revisions and epoch expiry prevent stale publication. Generic structured jobs remain explicit candidates pending generic collection integration. Name-only watches visibly report search_discovery_pending rather than pretending search ran; Brave/search implementation remains next work.

Ruff and strict mypy pass for the initial implementation. Synthetic database regressions are running for restart/replay, valid empty boards, invalid ATS replies, denied pages, changed companies, lost leases, unknown redirects and page caps. No live fetch/search/provider calls or dependency operations were made. Milestone 4 remains incomplete.

Persistent discovery targeted validation: twelve discovery tests plus five existing company/inventory API tests passed (17 total, 7.44s); Ruff and strict mypy pass. Added authenticated discovery history and recovery for a dispatcher-exhausted page operation, so an interrupted step cannot remain joined forever without being recorded. API type regeneration and production frontend build are running alongside the independent full backend regression suite. No browser journey or live discovery is claimed.

### Persistent official-URL discovery validated locally

Full backend suite passed 111 tests (42.48s); migration consistency reported no new upgrade operations. Generated API types and TypeScript/Vite build pass, with the existing 514 KB minified chunk warning. Final review identified potential lock inversion if source scheduling retained source locks while discovery acquired company locks; separated their transactions. All thirteen discovery regressions then passed (2.08s), including a separate collector connection acquiring company/source locks during the scheduling boundary. Ruff lint/format and strict mypy pass. No live fetching, search, model calls or browser UI changes were validated in this phase.

Saving the persistent official-URL/ATS discovery phase locally. Next implement Brave search with durable request budgets and ambiguity handling, generic source collection/pagination and browser/AI fallback, and display discovery evidence/coverage in the portal. Named-employer acceptance, matching, digests and production deployment/live gates remain part of the active full goal. No new dependency or environment blocker occurred.

### Brave search implementation checkpoint

Prior discovery phase is commit 2698ea0. Added the fixed Brave Web Search endpoint with a separate default-mock search mode, mounted key setting, durable per-epoch request slots/results, 300/day and configurable 1,000/calendar-month default budgets, and persisted rate-limit cooldown. Reservations count unknown/failed attempts conservatively and cannot be silently replayed. Search receives company-name queries only; private/duplicate result URLs are excluded and snippets are not promoted to jobs or verified identity. Name-only watches and exhausted unresolved website discovery now queue a search step; ambiguous leads remain review candidates.

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

Prior search/review phase is commit 3a8b8f9. Connected structured generic job pages to source discovery and the collection worker. Registration requires matching structured employer name or official employer URL; unverified and expired candidates are withheld. Generic sources are explicitly non-authoritative, with company identity captured in their source configuration. Collection preserves existing records on missing jobs, bad content types, unknown redirects or failures; job descriptions still enter the shared immutable revision flow. Initial targeted regressions are running. Pagination, generic AI/browser fallback and wider named-employer coverage remain unfinished; no live requests were made.

Generic integration follow-up: eighteen targeted generic/discovery tests passed (6.12s). Initial strict typing detected reuse of an evidence-dict loop variable for PageLink objects; renamed it. Added persisted generic page frontiers capped at 200, next/detail link traversal restricted to the watched site, and baseline finalization after a generic epoch with positive observations even when coverage remains partial. This prevents newly observed roles from being labelled baseline indefinitely on non-exhaustive sites. Validation of continuation/replay and baseline behavior follows.

Generic pagination checks: 26 generic/discovery/inventory tests passed (5.72s), then six targeted generic tests passed (2.71s) after adding persisted-frontier/replay and partial-baseline regression coverage. Source API now exposes authoritative coverage; the portal labels generic sources as Website sources with partial-site coverage and distinguishes saved sources from unverified candidates. Generated API contracts, frontend build and lint pass (156.79 KB gzipped JS; existing chunk warning). Full backend validation is in progress.

### Generic structured collection validated locally

The full backend suite passed 129 tests (56.75s). After the final duplicate-card guard, sixteen generic/inventory tests passed (6.22s), including bounded links, saved continuation, replay, first-observed baseline, later unrelated-function jobs, immutable revisions and omission safety. Generic pages do not refetch links already represented by accepted postings; repeated records in one epoch preserve the first accepted revision and flag unstable pagination rather than oscillating between card/detail content. Migration consistency, Ruff lint/format and strict mypy pass. Generated API/frontend build and lint passed before this final backend-only guard.

The earlier mypy failure was `Incompatible types in assignment (expression has type PageLink, variable has type dict[str, Any])` plus four associated attribute errors in discovery.py; the final renamed-loop-variable check passes. No dependencies or images were fetched, no live source/provider calls occurred, and no new browser journey was run for the static source/status labels. Saving this phase locally. Next: unstructured extraction/browser transport, conditional snapshots and source-specific coverage, followed by matching, notifications and remaining deployment/live acceptance. The full goal is active; no new environment blocker.

### Active browser dependency blocker

Generic collection phase is commit e9f9c25. Attempted `.venv/bin/uv add --project backend --default-index https://packages.example.invalid/python/simple 'playwright>=1.63,<2'`. It exited 2: `Failed to fetch: https://packages.example.invalid/python/simple/lxml/`; `client error (Connect)`; `invalid peer certificate: UnknownIssuer`. The command left pyproject.toml/uv.lock unchanged (clean Git status confirmed). No retry, registry switch, trust change or image/browser download was attempted. Browser dependency setup is stopped under the project network rule. Asked the user to resolve trust or explicitly authorize the previously successful command-local SSL_CERT_DIR exception for this new attempt. Earlier exception approval was for a completed setup attempt, not assumed blanket permission.

Unstructured extraction contracts and mocked validation can continue with installed dependencies while this browser setup blocker awaits user input. The full goal remains active; browser/deployment gates are not passed.

### Unstructured extraction contract validated while browser setup waits

Added a separate job_extraction OpenRouter schema/prompt using only page spans and observed links, with no CV/profile input. Titles, employers, descriptions and optional fields require exact span quotations; URLs must refer to observed link IDs; duplicate/ambiguous detail links and invented fields are rejected before the provider's bounded repair completes. Closed/uncertain status remains explicit. Seven synthetic tests passed (1.47s), plus Ruff and strict mypy (46 source files). These tests mock inference; no model quality or integrated collection acceptance is claimed. The extraction queue/persistence path still needs implementation.

Saving this contract work and the exact dependency blocker locally. Browser package installation remains stopped; no alternate dependency source, retry, certificate change or image download occurred. The goal remains active because other implementation work is available while the dependency question awaits the user.

### Broad matching policy checkpoint

Browser dependency setup remains stopped after the recorded UnknownIssuer failure; no new approval or retry has occurred. Continued independent matching implementation: profile-agnostic structured assessment, exact evidence validation, deterministic unrelated-function/required-criterion precedence, configurable 30-point inclusion, substantial versus possible categories and focus/expand/open domain handling. Missing or incomparable required facts stay uncertain; unsupported output raises an assessment error. Matching payloads omit nested original-CV quotations and redact unnecessary contact information.

Static checks pass. Synthetic tests cover threshold boundaries, function intent without title blacklists, preferred versus required constraints, domain diversification, salary uncertainty, invalid evidence and minimized task payloads. Persistence, worker/reassessment integration, current-versus-stale job views and notifications remain unfinished; no live model quality claim.

Matching persistence checkpoint: ten policy/assessment regressions passed (3.52s), including captured historical profile results, bounded reassessment, mode-change guard and profile-purge cleanup. Added an immutable assessment table keyed by job/profile/model/policy versions, AI-queue job handlers, continuation batches and policy-versioned idempotency keys. Profile deletion cascades through explanations and cancels pending/in-flight assessment operations. Original CV quotations are excluded from the matching payload.

Initial mypy check reported `Incompatible import of prepare` and two dependent type errors because discovery and matching used the same branch-local import name in operations.py. Aliased the matching preparation import; final static checks are running with the complete backend suite. Added explicit current-version lookup, stale model/profile tests, lost-lease and in-flight purge regressions. Browser dependency work remains stopped; no new dependency fetch or provider call occurred.

### Supplied CV format verification

2026-10-07: Rechecked the supplied ignored PDF with scripts/check-cv.py: one page with text, 3,847 extracted characters, zero AI requests and no persisted extracted content. Git-ignore check passed. Three targeted synthetic format regressions passed (3.06s): invalid/input limits and DOCX text, multi-page PDF, and DOCX body order with nested tables and merged cells. No parser changes were needed for this check. The parser remains generic; this sample does not establish arbitrary PDF column order, scanned/OCR support or semantic profile accuracy. Those limitations remain acceptance work. Existing matching work was left unchanged; browser dependency setup remains stopped at the previously recorded certificate error.

### Matching API integration checkpoint

Twenty matching/persistence/inventory regressions passed (4.22s). Added current-version shortlist queries, typed explanations, explicit stale status and current operation/error details to all-jobs and detail responses. Mock/live modes now have separate persisted assessment and operation identities, preventing synthetic decisions from becoming current after a mode change. Static checks initially found import ordering, one long string and optional-operation variable typing; corrected. New API/mode regressions and migration checks follow. The portal still needs to consume these fields; no live inference or dependency retry occurred.

### Broad matching and shortlist API validated locally

Full backend suite passed 159 tests (61.78s); the preceding targeted policy/persistence/API suite passed 26 tests (13.76s). Migration consistency reports no new upgrade operations; Ruff lint/format and strict mypy pass (49 application source files). Generated OpenAPI types and TypeScript/Vite build pass (156.79 KB gzipped JavaScript; existing chunk-size warning). Final static fixes were import ordering, line formatting and separating optional lookup variables from ORM iteration variables.

Validated coarse 30-point inclusion, unrelated-function precedence, unknown/required/domain handling, evidence validation, minimized profile payloads, bounded reassessment and replay, historical completion, lease loss, profile purge, current-versus-stale API behavior, both shortlist categories, rejection visibility in All jobs and mock/live separation. Provider inference was mocked at test boundaries; no live matching quality or integrated matching browser journey is claimed.

Saving this phase locally. Next implement portal explanations and status, explicit reassessment/feedback and mocked end-to-end matching fixtures; continue extraction integration, notifications and deployment acceptance. Browser dependency setup remains stopped at the previously recorded UnknownIssuer error, with no new retry or approval. The complete PLAN.md goal remains active.

### Assessment portal and owner actions checkpoint

Previous phase is commit 80eacf2. Added authenticated current-version reassessment that joins pending/successful work and explicitly retries terminal failures, including closed jobs. Added version-checked relevant/not-relevant feedback with optional notes, independent from AI categories and preferences, and cleared by profile purge. Fifteen assessment tests passed (15.92s). Static checks found a missing explicit None return after widening assess_intent to return an operation; corrected.

Portal now consumes current verdicts/evidence, labels mock results, shows stale/failure states, polls active assessments and offers owner feedback with conflict-preserved edits. Component/build checks are underway; no new dependency fetch or live provider call. Browser transport setup remains stopped at its recorded certificate failure.

Portal validation checkpoint: 161 backend tests passed (27.64s); the real API/database company/job browser journey passed in 6.3s (10.9s total), including feedback save/reload, retained filters, 375/1440 layouts with no overflow or axe violations. Mobile screenshot inspected. Added explicit reassessment Idempotency-Key receipts after contract review; sixteen targeted assessment tests pass (12.84s), including terminal-failure replay without another attempt and cross-job key rejection. Migration consistency passes. Frontend rerun found one stale test assertion expecting POST without the newly added header (16 passed/1 failed); updated the assertion and added ambiguous-network replay coverage. No dependency retry or live inference occurred.

### Assessment portal and feedback phase validated

Final frontend suite passes 19 tests (7.59s), including unknown-network request-key reuse and clearing cached explanations/feedback after profile purge. TypeScript/Vite build and ESLint pass (158.41 KB gzipped JavaScript; existing chunk warning); affected files are formatted. Backend full suite passed 161 tests before the final replay-key addition; sixteen targeted assessment regressions passed afterward, with Ruff/strict mypy and migration consistency passing. The single stale frontend POST assertion failure was corrected; no test failure remains in the final runs.

Real API/PostgreSQL/browser company/job journey passed (6.3s, 10.9s total), covering feedback persistence and filtered navigation; 375/1440 widths had no overflow or axe violations, and mobile screenshot was reviewed. Assessment explanation rendering is component-tested with synthetic reports; a worker-to-shortlist mocked browser journey remains pending. Purge copy now names assessment/feedback removal and its cached-data cleanup is component-tested. Saving the phase locally; next complete mock task fixtures and integrated assessment journey, then extraction/notification/deployment work. No new dependency attempt, live API call or production-network claim. The original PLAN.md goal remains active.

### Mocked assessment journey checkpoint

Previous phase is commit 87d2b4e. Added an explicit development-only AI fixture directory. Replay requires exact model, prompt text/version, schema version and task input; unknown inputs remain visibly blocked, duplicate/invalid fixtures fail, and normal output/evidence validation still runs. Production rejects fixture configuration; live mode rejects mock model IDs. Six authored matching examples cover both shortlist categories, unrelated functions and changed role preferences without a runtime profession-specific mock algorithm.

Thirty-eight fixture/matching/provider tests passed (13.56s), with no HTTP or billing records for fixture inference. Ruff/strict mypy (50 source files) and frontend build pass after formatting one long error string. Browser fixture generates synthetic files in its temporary directory and dispatches real durable intents every two seconds for workflow testing; production minute scheduling is unchanged. Added a real queue/worker-to-shortlist browser journey; execution follows. No live provider request or blocked dependency retry occurred.

Mock journey validation checkpoint: the new real API/queue/worker browser journey passed in 9.0s (15.1s total). It verified Relevant plus Possible entries, unrelated-role exclusion with All jobs access, evidence disclosure and automatic changed-preference reassessment. No overflow or axe violations at 375/1440; mobile screenshot reviewed. Full backend suite passed 165 tests (50.95s); Ruff/format/mypy and frontend build/lint/format pass. Screenshot review found weak subheading separation; adjusted assessment heading weight/spacing and quote wrapping. A final browser rerun will verify that polish and the accelerated fixture dispatcher across existing journeys.

Full browser run: seven existing journeys passed; the new eighth failed because its heading wait matched an already-existing Synthetic Entertainment card before navigation. The seed command received `companies` as the ID and exited 1 with `ValueError: badly formed hexadecimal UUID string`. This is a test synchronization issue evidenced by the command argument, not a dependency failure. Added an explicit company-detail UUID URL wait before reading the identifier; the full-suite rerun follows with frontend files stable.

The second full browser run passed the first seven journeys and reached matching, but timed out after 60s waiting for preference-triggered results. Read-only PostgreSQL evidence showed assessment intents still queued with attempts=0 and dispatched_at set, while procrastinate_jobs was empty. process_operation used SELECT FOR UPDATE SKIP LOCKED: a consumer could treat a dispatcher-locked existing row as missing, return success, and lose its queue entry until two-minute outbox recovery. Added a concurrent row-lock regression; it failed on the old code (exit 1, 0.42s), confirming the mechanism. Changed single-intent claims to wait for the lock with a 10-second database lock timeout; long stalls still retain the durable intent for recovery. Validation follows. The initial read-only probe used system Python and failed with ModuleNotFoundError: psycopg; rerunning with the already-installed backend virtualenv succeeded, without an install or dependency retry.

The dispatcher-lock regression now passes, alongside profile concurrency/recovery and assessment tests: 31 passed (10.33s). Ruff and strict mypy pass. Full backend and all eight real API/browser journeys are being rerun after this shared worker fix. Policy-upgrade reassessment reconciliation remains a matching lifecycle follow-up alongside the already-recorded live-quality and notification gates.

### Mock workflow and dispatch handoff validated

Final backend suite: 166 passed (86.40s). Final full real API/PostgreSQL/worker/browser suite: all eight journeys passed (1.8 minutes), including the new matching/preference-change journey (13.7s). The former single-intent SKIP LOCKED race is covered by a regression that failed before the fix and passes after it; existing concurrent claims, leases, purge and restart/recovery tests pass too. The earlier navigation race and preference-result timeout are resolved in the final run.

Ruff lint/format and strict mypy pass; frontend build/lint/format pass (158.41 KB gzipped JavaScript, existing chunk warning). The final matching views have no overflow/axe violations at 375/1440, and the updated mobile screenshot was reviewed. Synthetic fixture replay makes no provider call or billing record; this is workflow acceptance, not real-source coverage, model-quality acceptance or production isolation. Browser fixture servers exited.

Saving this phase locally. Next address policy-upgrade reassessment reconciliation and remaining generic extraction integration, then ntfy/digest/local operations and release gates. Python Playwright dependency setup remains stopped at the existing certificate blocker; no new fetch, trust workaround or live API request was made. The complete PLAN.md goal remains active.

### Matching policy reconciliation checkpoint

Previous phase is commit 842e18d. Added a bounded periodic reconciliation pass (100 active/unknown jobs per minute) that looks for missing current job/profile/model/policy/mode intents using their indexed deterministic keys. It handles policy upgrades, rollback with newer inventory, mode changes and restart without a volatile cursor. Existing failed/blocked/cancelled intents are not silently retried. Closed roles remain manual reassessment only; unmapped models and missing profiles skip the scan. Collection, explicit reassessment and profile fan-out now share intent construction. Fan-out captures policy version and refuses obsolete continuations.

Twenty-eight reconciliation/assessment/inventory regressions passed (13.44s), covering bounded batches, rollback, concurrent ticks, mode changes and failure deduplication. Ruff and strict mypy pass after import ordering cleanup. Full backend verification follows; no frontend change, dependency attempt or live API request occurred.

### Policy reconciliation validated

Full backend suite passed 170 tests (36.88s). After adding an explicit normal-control-tick wiring check, all five reconciliation tests passed (0.99s). Ruff lint/format and strict mypy pass. No schema/API response or frontend changes required a new migration or UI build. The periodic scan now fills missing current-policy intents independently of a new company observation, while preserving failed-call retry boundaries and manual handling for closed jobs.

Saving this phase locally. Reviewed generic collection and extraction integration: fetched visible text/observed links need a persisted handoff to the AI queue, with source/run revision guards and employer verification before accepting open roles. That integration remains the next implementation step; no extraction completion is claimed. The complete PLAN.md goal remains active, with the same stopped browser dependency setup and no new provider/dependency request.

### Example CV recheck (2026-10-07)

For the user-supplied example, reran scripts/check-cv.py: PDF text extraction succeeded (one page, 3,847 characters), with zero AI requests and no persisted extracted content. Git confirms the PDF is ignored. Existing synthetic PDF/DOCX format checks passed: 3 tests, 11 deselected, 1.57s; one existing Starlette/httpx deprecation warning. No parser changes or dependency installs were needed. This verifies text extraction only, not semantic accuracy, arbitrary column reading order or OCR. Existing uncommitted job-extraction integration work was left unchanged. Initial sandbox inspection failed with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` (exit 1); approved elevated local inspection/validation succeeded.

### Unstructured extraction integration checkpoint

Added a persisted bounded public-page snapshot and AI-queue handoff with captured task configuration/mode, exact evidence validation, open-status/employer guards, retry without refetch, and seven-day raw snapshot retention. Current source/run revision and operation lease checks prevent obsolete publication. Initial affected suite: 43 passed, 3 failed (9.95s, exit 1). Two old inventory tests stopped before the new AI continuation; updated them to complete that step. Discovery also registered a redundant generic source for an official page linking to a supported ATS; correcting that precedence. Earlier editing accidentally replaced retention.py with discovery text; static inspection caught it and the original retention code was restored before validation. Existing profile/retention tests passed in this run. Integration remains under validation; no dependency retry or live provider call.


### Persisted extraction locally validated

2026-10-07: Full backend suite passed 184 tests (75.02s), including snapshot replay/retry, missing-model explicit mapping, open/employer filtering, source/new-epoch/mode/lease invalidation, raw retention, input bounds and persisted pagination across fetch/AI queues. Existing CV retention and inventory omission protections pass. The initial three regressions were corrected: tests now execute the AI continuation and direct supported ATS links take precedence over plain careers-source registration. Ruff lint/format and strict mypy (52 application files) pass. Alembic check reports no new upgrade operations against migration 0012. One existing Starlette/httpx deprecation warning remains.

These are mocked-inference workflow checks, not real-source/model-quality or browser/network-isolation acceptance. No frontend response contract changed. Browser dependency setup remains stopped at the recorded UnknownIssuer error, with no dependency retry, trust workaround or live provider call. Saving this phase locally; next implement the timezone-aware notification scheduler and durable digest/delivery ledger. The complete PLAN.md goal remains active.


### Notification calendar foundation

Extraction phase saved as 69dd4b5. Added owner-timezone daily slot calculation, independent of the host timezone and collection interval. It chooses the first repeated occurrence and advances nonexistent minute-granular wall times to the first valid minute, including half-hour gaps and skipped dates. Future-slot calculation never schedules a downtime catch-up. Nine calendar tests passed (1.14s), covering London winter/summer/gap/fold, Lord Howe, Apia, owner-local dates and naive-time rejection. Ruff and strict mypy (53 files) pass. This is the calendar foundation only: persisted settings/slots, event and delivery ledgers, worker/API/UI wiring, ntfy transport and recovery remain to implement. No message was sent or dependency fetched. The complete goal remains active.

### Notification ledger checkpoint

Added migration 0013, a versioned owner schedule, assessment eligibility events committed with their assessments, unique local-date digest snapshots and durable event membership. Selection rechecks current job/profile/model/policy/mode and separates new, baseline and reassessment counts. Purge removes profile-derived digest content while retaining date receipts to prevent another digest that day. Initial ledger/assessment tests: 27 passed, 1 failed (13.99s, exit 1); the empty-summary fixture still had an active collection intent, so the summary correctly remained pending. Correcting that fixture. Initial lint/type checks found long generated lines and an untyped examples list; formatting/annotation fixes now pass Ruff and strict mypy (55 files). No delivery transport is implemented or message sent yet.


Notification integration checkpoint: 41 targeted calendar/ledger/assessment tests passed (8.89s), including concurrent ticks, full membership beyond ten example titles, new-versus-reassessment labels, local-date receipts after purge, late assessment carry-forward and authenticated settings/history revision handling. The empty-summary fixture issue is corrected. Added normal-control-tick wiring coverage and started the complete backend suite. Ruff/format and strict mypy pass (57 application files); regenerated OpenAPI types and frontend TypeScript/Vite build pass (158.41 KB gzipped JavaScript, existing chunk warning). No UI controls or delivery transport are claimed yet, and no notification/provider request occurred.


### Notification ledger validated locally

Full backend suite passed 210 tests (87.91s). Final policy review then added suppression for jobs already reserved/sent/ambiguous in the same integration mode and explicit current assessment-error/unresolved-watch/matching-availability fields. The resulting targeted ledger suite passed all 22 tests (5.57s); the preceding category/ambiguity cases passed 21 tests (9.12s). New qualifying roles from prior not-match results receive a reassessment label; possible/strong changes for already-notified roles do not alert again. Current failures are selected by current assessment identity, not historical failed operations.

Ruff lint/format and strict mypy pass (57 source files). Alembic consistency reports no new upgrade operations against migration 0013. OpenAPI types were regenerated and the final frontend TypeScript/Vite build passed (158.41 KB gzipped JavaScript). Existing Starlette/httpx deprecation and frontend chunk-size warnings remain. No dependency fetch, trust workaround, live AI request or ntfy publish occurred.

Next implement delivery attempts, bounded retry, ambiguous-send recovery and definitely-unsent membership release, followed by portal configuration/history and transport validation. Digests currently persist as pending/skipped; notification transport is not yet functional. The original PLAN.md goal remains active, and the Python browser dependency certificate blocker is unchanged.

### Notification delivery implementation checkpoint

Added durable per-attempt send records, the notify queue handler, pre-request sending persistence, bounded retries and conservative ambiguity recovery. A default mock notification mode performs no HTTP and cannot record a synthetic success as delivered. Captured destinations are rechecked before loading publisher credentials; redirects are not followed. Publisher message/response limits and privacy-safe error codes are implemented. Source contract checked against public ntfy publishing documentation. Initial static checks found two long message-format lines; corrected. Strict mypy passes (59 files); migration and runtime tests follow. No notification was sent or dependency fetched.

Delivery validation checkpoint: 40 targeted delivery/transport/ledger tests passed (9.00s). Verified sending-before-I/O, replay suppression, bounded connect-failure retry, deadline expiry, conservative 5xx/read/write ambiguity, redirect refusal, immutable destination checks and in-flight purge. Ruff and strict mypy pass (59 files). Adding safe latest-attempt details to notification history and an explicit crash-after-send-commit regression before the full suite. Default notification mock mode never makes HTTP or records a fake delivery receipt.

### Progress cadence reinforced

At the user's request, AGENTS.md now explicitly requires regular written checkpoints between implementation/validation batches, including during longer phases; commentary does not replace PROGRESS.md. The full backend suite is currently running (session 77636); no final result is claimed. Strict mypy passes (59 files). The latest Ruff run found one overlong notification-retry error string in backend/app/api/operations.py (E501, exit 1); shortening it before the final lint check. Latest completed targeted delivery/transport/ledger run remains 40 passed (9.00s). No real notification or dependency fetch occurred.

Regular validation checkpoint: AGENTS.md cadence rule is updated. Ruff lint/format now pass after shortening the retry message. Regenerated delivery-history API types and frontend TypeScript/Vite build pass (158.41 KB gzipped JavaScript; existing chunk warning). Full backend run remains active with no failure output so far; its result is not yet claimed. DEPLOYMENT.md, DATA_MODEL.md and API.md now describe actual send semantics and explicitly retain manual resend/test/UI/live-ntfy gates. No dependency retry or real publish occurred.

Full delivery regression run passed 235 tests (88.62s). It reported the existing Starlette/httpx warning and a new SQLAlchemy DISTINCT ON deprecation in latest-attempt history; replacing that query with a correlated maximum-attempt lookup. Final transport review found numeric Retry-After was capped to 30 minutes, which could shorten a longer server cooldown; preserving numeric/HTTP-date delays and checking persisted destination cooldowns across future digests. Adding regressions for both before saving the phase.

Post-review delivery checks passed 44 tests (22.77s), with only the existing Starlette/httpx warning; the DISTINCT ON deprecation is removed. Persisted rate-limit cooldowns now survive into later digests. A final focused check is running after extending numeric cooldown parsing to handle leading zeros and values beyond the representable calendar without an early retry. Static lint and type checks pass. No live ntfy request or dependency attempt occurred.


### Notification delivery locally validated

Full backend suite passed 235 tests (88.62s). After final recovery/cooldown refinements, 44 delivery/transport/ledger tests passed (22.77s), followed by 22 focused delivery/transport tests after large/padded Retry-After handling (8.97s). Ruff lint/format and strict mypy pass (59 files). Migration 0014 matches ORM metadata: Alembic check reports no new upgrade operations. Generated OpenAPI types and frontend TypeScript/Vite build pass (158.41 KB gzipped JavaScript). The SQLAlchemy DISTINCT ON warning was removed; the existing Starlette/httpx and frontend chunk-size warnings remain.

Validated persisted pre-send state, acceptance receipts, replay safety, bounded definite-failure retry, unknown-outcome reservation, crash recovery, in-flight purge, destination changes and cooldown carry-over without real publishing. AGENTS.md now explicitly requires regular written progress checkpoints, including during long phases, and the top-level progress summary is refreshed. Saving this phase locally. Manual resend/test-message actions, notification portal UX and actual local ntfy/deployment acceptance remain next; no release completion is claimed. The existing browser dependency certificate blocker remains unchanged and was not retried.

### Explicit notification actions checkpoint

Extending delivery records with independent retry batches and deadlines. Manual resends retain the original summary/date but start a fresh three-attempt, 30-minute window. Prior unknown sends remain protective if a subsequent resend definitely fails. Standalone test deliveries share transport/recovery without consuming a daily date or job events. Added replay-protected owner action contracts, expected-latest-delivery checks and required acknowledgement for ambiguous resends; another digest already holding the roles prevents stale manual duplication. Migration 0015 and runtime validation are next. No real publish, dependency fetch or change to the browser certificate blocker.

Owner-action backend checkpoint: 40 targeted action/delivery/ledger tests passed (13.89s), including standalone test retries, request replay, fresh manual windows, ambiguous acknowledgement, old-unknown protection, purge and newer-digest membership guards. Initial mypy optional-previous narrowing and migration line-length errors were corrected; strict mypy now passes (60 files). Applying ui-ux-pro-max guidance to the existing Settings page: visible labels, retained edits on conflicts, focused errors and explicit duplicate acknowledgement. No design-system replacement or dependency installation is needed.

Notification UI checkpoint: added schedule/timezone/empty-summary controls, independent test action, dated delivery history and explicit ambiguous resend acknowledgement to Settings. Draft schedules retain their revision and edits across conflicts; send request keys/bodies survive ambiguous network failures. Added explicit removed-content rendering and cleared notification-history cache on profile purge. The browser fixture now explicitly forces notification mock mode. Initial frontend build/lint passed (161.70 KB gzipped JavaScript, existing chunk warning); four new interaction/privacy tests and the refreshed build are running before isolated browser validation.

UI validation correction: initial frontend suite passed 22 tests and failed one new schedule-conflict test. Its mocked server kept returning revision 1 after the test injected revision 2 into the cache, so the expected newer-schedule action correctly disappeared on refetch; the fixture now retains the newer server revision. TypeScript also rejected an empty synthetic purged snapshot because the API serializes default coverage fields; corrected that fixture to match the actual response. Backend Ruff found one import-order issue after adding publisher metadata; correcting it. Full backend tests remain running independently.

The UI conflict rerun still failed because the editing script updated the mocked read but missed the one-line assignment of the new server revision. Inspection confirmed the fixture still left its server variable at revision 1; corrected that exact assignment. This was a test-fixture edit omission, not a product change. Final backend Ruff/format/mypy checks now pass (60 files). Frontend rerun follows once the active build exits; no browser run has started yet.

### Progress logging rule confirmed — 2026-10-07

Confirmed the regular-update requirement in AGENTS.md and reinforced it with an explicit resume checkpoint: read the latest progress entry and reconcile completed checks or changed blockers before starting another batch. Written updates remain required between meaningful implementation/validation batches, during longer phases, immediately on blocker changes and before handoff; commentary alone is insufficient. This documentation-only update preserves the ongoing notification implementation and its outstanding browser/migration validation. No tests, dependency fetches or runtime changes were performed for this update.

### Notification acceptance resumed — 2026-10-07

Reconciled the previous validation results: full backend suite passed 245 tests (118.74s); frontend suite passed 23 tests across eight files, with ESLint and Prettier passing. Backend Ruff/format and strict mypy passed (60 application files). The latest frontend build passed at 161.85 KB gzipped JavaScript, with the existing chunk-size warning. Fresh Alembic check against the disposable test database reports no new upgrade operations for migration 0015. Started the isolated nine-journey browser suite using installed Chrome and mock providers; the first journey passed and the suite remains running. No frontend mutations/builds/unit tests will overlap that run. The Python Playwright certificate blocker is unchanged; no dependency retry or real notification occurred.

Browser checkpoint: all nine real API/database/worker/browser journeys passed (1.3 minutes), including notification schedule save/reload and an explicit mock test delivery (6.2s). Notification axe/overflow checks passed at 375, 768 and 1440 pixels, plus a landscape/reduced-motion/enlarged-text overflow check. Mobile and desktop screenshots inspected. Desktop inspection found the inherited generic action-card styling unnecessarily boxed/stretched the schedule button and time input; applying scoped spacing/alignment CSS, then rerunning only the affected notification journey. No functional failure or real publish occurred.

### Notification owner controls locally validated

The full nine-journey browser suite passed (1.3m). After the scoped notification form CSS correction, the affected real API/worker journey passed again (16.2s; 25.7s total), including responsive/axe checks; final desktop screenshot inspected. Production build passes at 161.85 KB gzipped JavaScript. Migration 0015 is consistent with ORM metadata. Prior completed backend/component/static evidence is recorded above. Explicit tests consume neither job events nor daily dates; manual resends retain original dated content, use fresh bounded retry batches and require acknowledgement of unknown originals. Documentation now reflects implemented behavior. Real local ntfy acceptance, live provider/source validation and production deployment remain pending. Saving this validated phase locally; the full PLAN.md objective remains active.

### Company coverage implementation checkpoint

Notification phase saved as 754fa70. Implementing batched company summaries: distinct collected-job counts by availability, enabled/limited/error/unverified source counts, latest attempted versus successful source checks, and next collection/discovery times. Paused watches will not advertise a scheduled check, and source cooldowns will be respected. Counts describe the stored inventory only; no-source, partial and failed coverage remain explicit. This is in-progress implementation, not validated acceptance yet.

Company coverage validation checkpoint: seven focused API/count tests passed (4.14s), including deduplication across sources, availability counts, disabled-source exclusion from scheduling, cooldown handling and paused/no-source distinctions. Ruff and strict mypy pass (61 application files). Initial Ruff line-length finding was resolved by formatting. A UI editing command used the frontend working directory with root-relative paths and failed before modifying files; reran from the correct repository root. Added source-card pause/disable scheduling copy and browser assertions for company list/detail counts; final frontend checks and the affected browser journey are next.

Frontend build found the discovery test fixture omitted the required serialized coverage counters (TS2322); filled in the synthetic zero counters to match the generated API type. No runtime failure or dependency attempt occurred.

Company overview production build passed (162.35 KB gzipped JavaScript; existing chunk warning). Final backend Ruff/format passes (112 files); strict mypy previously passed (61 application files). Full backend and final frontend suites remain running. API/UI documents now specify that total counts include all availability states, dates do not imply all-source success, and pending discovery is distinct from collection scheduling.

Company browser checkpoint: both affected real API/database journeys passed (50.0s total): company source controls/counts/list-detail navigation (26.9s) and candidate confirmation (10.3s). Company count/coverage views passed axe and overflow checks at 375/1440; screenshots inspected. Correcting singular/plural source/role labels found in screenshot review; no behavior changes. Frontend previously passed all 23 component tests, lint and formatting. Full backend regression remains running with no failure output so far.

### Company coverage locally validated

Full backend suite passed 247 tests (135.60s), with only the existing Starlette/httpx warning. Seven focused inventory/overview tests passed earlier. Ruff/format and strict mypy pass (61 application files). Frontend component suite passed 23 tests; generated API types, production build, lint and formatting passed before final copy-only pluralization. Both affected browser journeys passed (50.0s), including count persistence on detail/list navigation and source pause behavior, zero axe violations/no overflow at 375/1440, and inspected screenshots. Final production build/lint passed after the pluralization-only correction (162.41 KB gzipped JavaScript, existing chunk warning); no further browser rerun is needed for that copy change. No migration was required.

The full PLAN.md goal remains active. Outstanding work includes conditional source snapshots, generic selectors/browser fallback, company-detail job-list presentation, complete deployment/backup/restore and representative live source/model/ntfy checks. Python browser dependency setup remains stopped at the recorded UnknownIssuer error; no retry, trust workaround or live provider request occurred.

### Conditional collection snapshot implementation

Previous company coverage phase saved as 6aef3bd. Implementing source/revision/URL-scoped public HTTP snapshots with seven-day expiry and a 200-page-per-source cap. Conditional requests always revalidate remotely; cache misses, corruption, expired entries and source edits require full responses. A 304 without usable conditional input is a visible failure, never an empty inventory. Accepted content is reparsed with current logic; snapshot writes share the existing lease-checked inventory/extraction transaction. Redirected pages, Vary responses and no-store responses are excluded from reuse. RFC 9111 conditional validation semantics were reviewed. Implementation/migration tests are next; no live source fetch or dependency retry occurred.

Conditional-snapshot checkpoint: strict mypy passes (62 application files) after making the generic fetch boundary export explicit. Initial focused run reached one failure in an existing inventory test: its stale runner import was removed while moving mocks to the actual HTTP-document boundary (Ruff F821). Restored that import; new conditional tests were passing in the same run. Added explicit redirect provenance so even a redirect chain returning to the original URL cannot treat a validator-stripped 304 as valid. Bodyless 304s now bypass decompression while retaining robots/pacing checks. No network/source calls or dependency attempts occurred.

Conditional snapshot validation checkpoint: all 61 focused inventory/generic/extraction/fetcher tests passed (22.42s), with the existing Starlette/httpx warning. The previous run had 41 passes and one stale-import failure, now corrected. Added a final updated-body/new-validator regression before the full backend suite. Verified repeated 304s do not create revisions or omissions, invalidated caches do not send validators, current expiry rules rerun on cached HTML, and source changes/lost leases prevent snapshot writes. Strict mypy and Ruff passed before the final regression; final static/migration checks and the full suite are running.

Final snapshot review: migration 0016 Alembic check reports no new upgrade operations, and Ruff/format/mypy pass. Full suite is running. Retention inspection found the initial batch implementation loaded up to 100 full page bodies just to delete expired entries; replaced it with a bounded key-only DELETE/RETURNING query to avoid that memory spike. This final change will receive the existing cap/expiry regression after the full suite exits.

Full conditional-snapshot regression suite passed 268 tests (73.87s), with only the existing Starlette/httpx warning. Migration 0016 is consistent with ORM metadata. Final Ruff/format/mypy pass (62 application files). Running only the existing cap/expiry regression for the final key-only retention query; no frontend contracts changed and no browser rerun is needed for this backend-only slice. All HTTP responses were synthetic. Live employer behavior, browser fallback and network isolation remain unverified.

### Conditional snapshots locally validated

The final cap/expiry regression passed (0.72s) after changing retention to key-only deletion. Full backend evidence remains 268 passed (73.87s), with static and migration consistency checks passing. Snapshot support is ready for later real-source validation; no release or isolation completion is claimed. Saving the phase locally. The existing Python Playwright UnknownIssuer dependency blocker remains unchanged, with no retry or workaround. Next continue declarative source configuration and remaining collection/UI/deployment work.

### Company-scoped job list implementation

Conditional snapshot phase saved as 99422cf. Extracting a shared job list into company detail, preserving company scope across filters and the Shortlist/All jobs switch. Adding list return/scroll restoration and deliberate refresh to avoid rearranging cached results while reading. Default availability is now active-or-unknown, with explicit active-only, unknown, closed and all-status filters retained. Correcting a matching availability gap: a saved task configuration with no model must remain unavailable, rather than masquerading as an empty shortlist. Implementation checks follow; no dependency retry or live provider call.

Shared-list review: preserved normal refetch-on-mount so returning from a profile/model change cannot indefinitely show an old cached shortlist or missing-model error. Background focus refetch remains off while reading, with an explicit Refresh jobs action. Scroll restoration waits for the returning list fetch to finish. Added backend tests for active/unknown defaults and saved-but-unmapped model configuration, plus component/browser assertions for fixed company scope and return navigation.

Company job-list validation checkpoint: 23 focused backend inventory/assessment tests passed (7.38s). Ruff and strict mypy pass (62 application files). Frontend suite passed all 25 tests across nine files; build/lint/format passed. Final refetch/scroll dependency adjustment is receiving a fresh build/lint and targeted list-test check before the isolated browser suite. The shared browser journey now covers inline company filtering, retained company scope, detail return and scroll restoration, plus responsive/axe checks. No browser acceptance is claimed yet.

Final shared-list build and ESLint passed (162.93 KB gzipped JavaScript, existing chunk warning); the two focused list interaction tests passed after the refetch/scroll refinement. Backend format check also passes (115 files). Started the isolated full nine-journey browser suite; frontend edits, builds and Vitest are paused until it exits. Current API/UI changes have no database migration.

Browser validation found an actual accessibility regression: seven journeys passed, but company and discovery journeys failed axe link-in-text-block checks (suite exit 1, 1.0m). The new missing-model notice used inline links distinguished only by color, with 2.26:1 contrast against surrounding text. Added a scoped underline to those links. The suite has exited, so frontend mutations are safe; rebuilding before rerunning the two affected journeys. No backend/runtime blocker was found.

Return-navigation review added keyboard focus restoration to the saved job link and native browser-back assertions. Also guarded cached shortlist rendering when a revalidation reports matching_unavailable, so removing a model cannot leave old shortlist cards visible beneath the configuration notice. Adding a focused regression for that cached-data case before the affected browser rerun. The link-underline correction builds/lints successfully; final navigation refinement checks follow.

Final navigation/cache guards now pass production build and ESLint (162.99 KB gzipped JavaScript), plus five focused list/data-purge component tests (3.86s). Started the isolated company/discovery browser rerun after the prior full suite finished with seven passes and two evidenced accessibility failures. Frontend files/builds/tests remain frozen during this rerun.

### Company-scoped job browsing locally validated

The affected company/discovery browser rerun passed both journeys (38.1s total; 21.5s company, 7.9s discovery). The company journey now verifies inline All jobs filtering, clear-filter company scope, return-link and native browser-back navigation, scroll restoration and restored focus on the originating job link. Company job lists have zero axe violations/no horizontal overflow at 375/768/1440; mobile/desktop screenshots inspected. The earlier complete nine-journey run passed seven and exposed the two inline-link accessibility failures now corrected; no claim of a single final all-nine run is made.

Backend: 23 affected inventory/assessment tests passed (7.38s), with Ruff/format/mypy passing (62 application files). Frontend: the earlier full suite passed 25 tests; five affected list/purge tests passed after final cache/focus refinements (3.86s). Final build and ESLint pass (162.99 KB gzipped JavaScript; existing chunk warning). Generated API types reflect active-or-unknown defaults while retaining explicit old availability filters. No migration or live provider call was needed. Saving the validated phase locally. Declarative selectors, browser fallback, automatic new-results indicators, route splitting, deployment/restore and live acceptance remain unfinished. Python dependency certificate blocker is unchanged; no retry or workaround.

### Declarative website extraction implementation

Company job browsing saved as 7329df3. Implementing explicit, bounded CSS rules for repeated job cards, required title/link/description/employer evidence, optional location/expiry/closed markers, same-site next links and an explicit empty-state marker. Rules use existing Beautiful Soup selection, with recursive pseudo-classes/scripts/selector lists excluded and HTML/node/card limits. Saving rules selects deterministic extraction for that source; clearing restores automatic JSON-LD/AI behavior. Employer verification and non-authoritative closure rules remain mandatory. Adding revision-checked configuration plus preview from a recent saved public page, with no preview fetch or AI call. Parser/API validation follows; portal controls and rendered load-more remain pending.

### 2026-10-07 — Progress recording rule reinforced

Confirmed and strengthened AGENTS.md: update this log regularly between implementation and validation batches, during unfinished phases, immediately on blocker changes, and before handoff. Each checkpoint must state the task, changes, completed validation, blockers and next step. This update changes documentation only; existing extraction implementation remains in progress and its validation is not claimed. The initial documentation inspection could not start in the sandbox (`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`, exit 1); the authorized escalated read succeeded. No dependency fetch was attempted. Next implementation work should reconcile the outstanding declarative-selector checks before continuing.

Selector validation checkpoint: resumed the existing implementation and confirmed no older Ruff/mypy/pytest process remained active. Strict mypy passes for 63 application files. Hardened cached preview validation so malformed documents, non-HTML/error responses and body mismatches return a clear unavailable-preview response; invalid stored empty rules no longer silently choose automatic extraction. Added synthetic selector and API regressions covering employer identity, field ambiguity, explicit empty states, expiry, pagination, revision conflicts and cache-only previews. Focused tests are running. Ruff found one overlong diagnostic string, now wrapped; final lint and test outcomes remain pending.

Selector focused checks passed: 24 parser/API/generic-inventory tests (7.86s), with the existing Starlette/httpx deprecation warning. Added a worker regression for persisted rules and three explicit empty-page checks preserving existing jobs without AI handoff. Full backend regression is running; Ruff passes after the diagnostic wrap. Regenerating API types and building the existing frontend to verify compatibility. API/source documentation now describes explicit rules, employer verification, snapshot-only preview and its cache-availability limits. Portal editing and rendered pagination remain unfinished.

### Declarative extraction backend locally validated

Full backend suite passed 287 tests (73.70s); the existing Starlette/httpx warning remains. The persisted-rule worker regression confirms repeated explicit empty pages never close generic-source jobs or trigger AI handoff. Ruff, format (117 files), strict mypy (63 application files), generated API types and production build pass (162.99 KB gzipped JavaScript; existing chunk warning). Documentation distinguishes this backend capability from the pending portal editor/rendered fallback. No new migration, live fetch/provider request or dependency retry occurred. A read-only lookup initially guessed a nonexistent frontend component path (sed exit 2); located the actual source controls in frontend/src/features/inventory/companies.tsx. Next implement the source-card rule editor with retained conflict drafts and saved-page preview, then validate the browser workflow. Deployment and the known Python Playwright certificate blocker remain outstanding; the full plan is not complete.

### Source rule portal implementation

Backend rules phase saved as 3dd8059. Adding an advanced website-source editor with required labelled selectors, optional fields, saved-page timestamp/coverage preview, automatic-mode restoration and revision-conflict comparison. Drafts survive background source refreshes; preview results are cleared when inputs change. Applying existing UI styling and the UI/UX skill form-feedback guidance. Component and real browser validation follow; no dependency retry or live provider request occurred.

Source editor checkpoint: all 28 frontend component tests passed (3.13s), including retained conflict drafts and stale-preview invalidation. The first implementation build/lint passed; the subsequent build with new test fixtures failed because the fixture omitted the required employer_scope API field (TS2741/TS2322). Correcting the synthetic fixture before browser validation. Browser seeder import/line-length lint findings were corrected; no application runtime or dependency failure occurred. Added an isolated real API/browser journey for preview, persisted custom rules and restoring automatic extraction, including responsive/axe checks.

Fixture follow-up: TypeScript also required baseline_at on the synthetic SourceView; added it. Final interaction review disabled conflict-choice buttons during requests and corrected singular job-count copy. Rechecking build/lint/component tests before freezing frontend files for the browser run.

Final source-editor static/component checks pass: production build (164.78 KB gzipped JavaScript, existing chunk warning), ESLint, Prettier, all 28 component tests (13.70s), plus Ruff/format for the synthetic browser seeder. Starting the isolated new real API/browser journey now; frontend files, builds and component tests remain frozen until it exits.

Source editor browser checkpoint: the new real API/database journey passed (16.5s; 25.4s total), including saved-page preview, custom-rule persistence after reload and restoring automatic extraction. Axe/overflow checks passed at 375/768/1440; screenshots inspected. Desktop screenshot review found inherited form-action styling unnecessarily boxed and stretched buttons. Applying scoped action spacing and a readable form width now that the browser process has exited; rebuild and affected rerun follow. No live website/AI call occurred.

### Website extraction portal locally validated

Final affected browser rerun passed (12.8s journey; 20.9s total) after the scoped width/action-layout correction; final desktop screenshot inspected. Preview/save/reload/restore flow and axe/overflow at 375/768/1440 pass. All 28 component tests passed before the CSS-only correction; final production build and ESLint pass (164.78 KB gzipped JavaScript), with seeder Ruff/format passing. No broader test rerun is needed for the isolated layout correction. Plan/source/UI/validation documents now reflect implemented portal controls.

Next prioritize the incomplete Docker delivery layer: current compose.yaml still lacks workers/fetcher/ntfy and references missing deploy/frontend.Dockerfile. Implement configuration and operation scripts without retrying blocked dependency downloads, then validate available local paths and report external-runtime gates precisely. Browser fallback/Python Playwright installation remains blocked by the previously recorded UnknownIssuer error. Live provider/source acceptance, production isolation, backup/restore and remaining UI polish are not complete. The full PLAN.md objective remains active.

### Docker delivery wiring in progress

Portal phase saved as 2dfdd7f. Inspected current Compose/backend/fetcher/worker entry points and cached images without fetching. Consolidating worker/AI worker/queue bootstrap/fetcher/proxy/local ntfy/edge into the main Compose file, retaining the old fetch overlay as a no-op compatibility file. Added the missing multistage frontend image, private LAN/tailnet Caddy listeners, deny-all ntfy configuration and explicit non-secret deployment parameters. Cached Python/Node/Caddy/PostgreSQL/Squid digests are used; ntfy digest remains a required installation input because its image is not cached or validated. Fetch isolation remains hard-disabled. No image build/dependency fetch, host firewall/route change or production startup has occurred. Configuration validation and deployment preflight follow.

Deployment configuration checkpoint: Compose service/network/port/secret-scope assertions pass using explicit synthetic non-secret parameters and a configuration-only ntfy digest. Removed a frontend Dockerfile COPY of a nonexistent public directory. Fixed one diagnostic line-length lint finding. The new build definitions have not been executed because backend dependency setup is already blocked.

New runtime validation blocker: the cached Caddy configuration check failed before Caddy executed, with `exec /usr/bin/caddy: operation not permitted` (exit 255). The operation was `docker run --rm --pull never --network none --read-only --cap-drop ALL --user 10001:10001`, tmpfs mounts for /data and /config owned by 10001 plus /tmp, a read-only deploy/Caddyfile mount, synthetic LAN_HOST/TAILNET_HOST environment values, image `caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f`, command `caddy adapt --config /etc/caddy/Caddyfile --validate`. No image pull or host networking was used. This proves only an execution failure, not a Caddy syntax failure or its cause. Container permission/security relaxation was not attempted. User/deployment-host assistance is needed for actual Caddy runtime validation; independent configuration work continues.

Secret-permission review: Compose file-backed secrets retain host file permissions, so mode-0600 files owned by the host user cannot be assumed readable by UID 10001 or PostgreSQL. Use readable secret files inside an owner-only 0700 host directory and mount each secret only into its designated services; no secret contents or current file modes were changed by this work. Deployment preflight/documentation must make this requirement explicit.

Deployment preflight checkpoint: the template passes and six deliberately unsafe variants are rejected (API publishing, all-interface edge bind, fetcher/core membership, fetcher DB secret, non-internal fetch network and floating PostgreSQL image). Added non-destructive deployment-input preparation and actual-secret readability checks; neither initializer nor real-secret checks have been run against user files. Public primary Caddy/ntfy/Docker documentation informed the configs. Identified an additional deployment portability gate: npm and uv lockfiles contain private package-registry URLs. They remain unchanged; portable off-network dependency locks must be prepared/validated on the intended host. No failed dependency command was retried. Caddy execution, normal Docker networking, browser fetching, ntfy image/runtime, backup/restore and ingress acceptance remain pending.

2026-10-08: synthetic deployment initialization passed in a temporary directory, including repeated-run preservation, expected file modes and rejection of a non-private secret directory. Ruff/format pass for all 13 scripts. A single new `docker pull binwiederhier/ntfy:v2.27.0` is now running to obtain the selected official release digest; this is not a retry of the blocked Python dependency operation. If it fails, stop without alternate registries or trust changes. Caddy validation remains blocked and was not retried.

ntfy pull completed successfully (exit 0), digest sha256:f2419f405127afa868f10985c1a41449e673477cee1eb19994339a5ae8b592e7; a network-none/cap-drop executable check reports ntfy version 2.27.0. Pinned that default in Compose and the example. Read-only Caddy diagnosis found `/usr/bin/caddy cap_net_bind_service=ep`. Its file capability conflicts with the intended cap-drop-ALL execution path; our high container ports need no such capability. Added removal in an independent runtime-base Dockerfile stage, keeping non-root/read-only/cap-drop security unchanged. Building only that cached runtime stage without package installation; full frontend/backend builds remain unverified.

Caddy execution blocker resolved by the project image fix: cached runtime-base build succeeded with the unnecessary binary file capability removed, and the same non-root/read-only/cap-drop-ALL/no-network adapt --validate check now exits 0. No host networking or security relaxation was needed. Full frontend build/service routing remains unverified. The non-root ntfy image also built successfully from the cached pinned release without package installs. An edit helper had an unterminated string literal and stopped before modifying its target files; corrected it and applied the intended ntfy readiness wiring. Isolated runtime checks follow.

Isolated ntfy runtime validation passed using the new non-root image, network none, read-only filesystem, dropped capabilities and temporary state. Verified healthy startup, anonymous publish/read denial, publish-only bearer token acceptance with a receipt, publisher read/unrelated-topic denial, reader publish denial and reader access to that cached receipt. The container was removed; no actual user credentials, network access or recipients were involved. Tightened Compose health matching to require healthy=true and added execution of that exact health command to the checker; affected rerun follows. Documentation now marks the Caddy file-capability issue resolved and distinguishes isolated ntfy acceptance from still-pending Compose/application/phone delivery.

### Docker configuration and isolated ntfy phase validated

Final ntfy checker rerun passed, including the exact tightened Compose health command. Template checks pass; Ruff/format pass for all 14 scripts and git diff --check is clean. Caddy runtime-base and non-root ntfy image builds/configuration checks are evidenced above. Main Compose now includes ten services; fetch overlay is retained as a compatibility no-op. README/PLAN/DEPLOYMENT/VALIDATION reflect the actual limits, including resolved Caddy capability failure. Saving this locally validated configuration slice; no full deployment or complete-goal claim.

Next implement and validate backup/restore operation scripts and remaining UI release polish, while keeping the Python Playwright dependency setup stopped at UnknownIssuer. Full image dependency builds/off-network lock portability, normal Docker bridge and stateful fetch isolation, real application ntfy delivery, live providers/sources and host ingress require later acceptance. No user credential or root .env was changed.

### Route loading and bundle reduction

Deployment wiring saved as 93a7d2e. Continuing independent release work while dependency/network gates remain open: splitting inventory/profile/settings routes with React lazy imports and retaining the navigation shell during loading or route errors. Route changes focus the main landmark when a lazy heading is not yet available, while existing list-return restoration remains responsible for the originating job link. Moving Settings out of the initial app module. Component/build and full browser navigation checks follow; no dependency retry.

Route-splitting checkpoint: production build passes with initial JavaScript reduced from 164.78 KB to 137.34 KB gzip, and separate inventory/profile/settings chunks. The oversized-chunk warning is gone. Existing 28 component tests and ESLint passed. Added focused slow-load and route-error boundary tests plus a browser failed-import/reload recovery journey; final checks and the full browser suite follow. No backend behavior changed.

Final route-loading checks pass: all 30 component tests (3.86s), build at 137.34 KB gzip initial JavaScript without the previous chunk warning, ESLint and Prettier. Starting the full 11-journey browser suite, including the new failed-import recovery path. Frontend files/builds/Vitest remain frozen until this process exits.

Browser checkpoint: the first five real API/database journeys passed (CV review/preferences, model settings, data purge, profile conflict recovery and billing recovery). The full 11-journey process is still running; frontend remains frozen. Read-only preparation for the next recovery phase confirms gpg, openssl and tar are installed locally; no dependency install or backup operation was attempted.

### Route splitting locally validated

All 11 browser journeys passed (2.3m), including preserved company-list focus/scroll, profile/settings workflows and explicit failed-page-download navigation/reload recovery (4.0s). Final build/lint/format and all 30 component tests passed as recorded above; initial JavaScript is 137.34 KB gzip without the prior chunk warning. Existing error handling remains at the application root, with an embedded route boundary retaining navigation. Documentation reflects the completed slice and limits. Saving a local commit; the full plan is still active.

Next implement encrypted backup and isolated restore tooling using available local tools and synthetic data. Remaining blockers/gates include Python Playwright UnknownIssuer, dependency lockfile portability, deployment bridge/firewall isolation, full image builds, application-to-ntfy delivery, actual private ingress, live source/model quality, and the new-results UI indicator. No dependency retry, live provider request or deployment startup occurred in this phase.

### Encrypted backup implementation

Route-loading phase saved as ccae444. Implementing streaming public-key encrypted snapshots of PostgreSQL custom-format dumps and documents/ntfy/Caddy/fetch-state volumes, with an encrypted checksum manifest. Backup probes the recipient before pausing writes, refuses missing volumes and unsupported service states, uses cached network-none read-only helpers, records restart instructions, and attempts recovery of previously active services even after partial stop or stream failure. Added decrypt-to-null verification for manifest/payload integrity. No real backup or production service stop has occurred. Failure-path and synthetic GPG checks follow; isolated restore, retention and scheduling remain pending. Initial Ruff findings were long strings/docstrings, now wrapped.

Backup validation checkpoint: six initial synthetic GPG/failure tests passed (1.85s), covering encryption/decryption, corruption, source failure, bounded timeout, partial-stop recovery and preservation of intentionally stopped services. Added payload-authentication checks after a forged checksum update, symlink rejection and an opt-in real PostgreSQL encrypted dump/restore roundtrip in newly created jobfinder_test_recovery_* databases. Durably flush the recovery journal and backup directory metadata before publishing a completed snapshot. A small docstring-edit helper failed with NameError before changing its file; corrected it. Final SQL fixture line-length findings are being wrapped. No production writers or data have been touched.

Resume checkpoint: no backup/test/pg_restore process remains active. The last completed opt-in recovery suite passed nine tests (4.707s), including a real encrypted PostgreSQL custom-dump/restore roundtrip in newly created disposable test databases, payload authentication after checksum replacement, and symlink rejection. Final Ruff checks passed after wrapping synthetic SQL fixtures. Those results are now reconciled with this log; no production backup was taken. Continuing archive and orchestration review before claiming the backup slice validated.

Backup archive review added actual container/project/volume binding checks before any writer stop, with drift rejection tested. Captured image/container identities will accompany encrypted metadata. Added a real disposable Docker-volume test for encryption of a UID-10001 file with mode 0600, verifying its archive contents and permissions after decryption. The test uses cached images and network none; no host networking exception or dependency fetch is introduced. The expanded recovery suite is running; one synthetic helper string needed line wrapping.

Expanded recovery suite: 10 checks passed; the PostgreSQL roundtrip errored before database creation because jobfinder-test-db-1 is stopped. `docker inspect` confirms state exited with the approved command listen_addresses=127.0.0.1/port=55439; pg_isready/psql cannot execute in a stopped container. This is an environment-state failure, not a dependency download failure or encryption regression. Restarting only the already-approved cached development database, then revalidating its loopback listener and rerunning the affected check. No test-created database was created by the failed attempt.

Development DB recovered using the existing host-network test override and --pull never. Fresh checks confirm LISTEN only 127.0.0.1:55439 and PostgreSQL listen_addresses=127.0.0.1. The affected real encrypted PostgreSQL roundtrip passed (1.051s); the earlier ten passing checks remain valid. Added atomic recovery-journal replacement and bounded Compose --wait checks so recovery does not equate a start request with a running/healthy service. Adding public-key-only encryption validation; no operator decryption key is required on a daily backup host.


### Advisory review assessed — 2026-10-08

Read the user-supplied REVIEW.md alongside CONTEXT.md, PLAN.md, DECISIONS.md, current progress, deployment recovery requirements and sampled operation/queue implementation. Agree with its central sequencing concern: synthetic/local validation does not establish real employer coverage, model usefulness, device delivery or intended-host operability. The queue duplication concern is a simplification candidate, not evidence that recovery can safely be deleted: sampled code uses leases and commit-time token checks to reject stale completions, plus explicit handling of the dispatch/claim race. No full correctness audit or fresh application test run was performed for this advisory assessment.

Updated PLAN.md with the next acceptance priority: finish basic backup/restore, defer optional polish/new capabilities, then prove a small representative real journey on the intended host before broadening acceptance. Keep original requirements and deployment gates; no rewrite, queue refactor, live API authorization or dependency workaround is inferred from the advisory. REVIEW.md is left unchanged, as are the in-progress backup scripts.

Reconciled preceding recovery validation: `JOBFINDER_RECOVERY_TEST_DB_CONTAINER=jobfinder-test-db-1 python3 -m unittest discover -s scripts -p test_recovery.py -v` completed with 12 passing tests in 3.861s (exit 0), including public-key-only encryption, real disposable PostgreSQL dump/restore and a disposable volume archive. This was the preceding completed run, not rerun during the review. It does not establish full deployment backup/restore; writer orchestration failure checks are mocked and the operator restore path remains unfinished.

Review inspection initially could not start in the sandbox: `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` (exit 1). Authorized elevated local file reads succeeded; this was a sandbox startup failure, not a dependency fetch failure. Existing Python Playwright UnknownIssuer and intended-host/network/provider acceptance gates remain unchanged. Next implementation task: finish the smallest safe isolated restore path and its focused validation, then surface the concrete host/live prerequisites instead of adding peripheral features.


### Isolated restore implementation checkpoint — 2026-10-08

Added an operator restore command that verifies encrypted payloads before creating fresh UUID-named volumes, streams archive contents into network-none helpers, and restores PostgreSQL in a network-none container with TCP listening disabled. Application services and notifications are never started. A private journal records retained volumes and partial failures; temporary containers are removed. Archive extraction accepts only regular files/directories, uses traversal protection and private permissions, and bounds entry count/expanded size. This is implementation in progress, not a validated restore claim. Next run focused extraction/failure checks and a disposable full restore drill; no production state or dependency fetch has been touched.

Restore validation checkpoint: the expanded recovery command ran 15 tests; 14 passed and the new complete restore drill failed at fresh-volume initialization (`docker run ... --cap-drop ALL --cap-add CHOWN ...`, exit 1). Inspection found the helper changed ownership before chmod, leaving root without ownership or FOWNER capability for chmod. Reordered chmod before chown, retaining the restricted capability set. This is a local implementation failure, not a dependency failure; test cleanup removed its disposable resources. Removed a redundant SQL probe and its lint finding. Rerunning the affected drill before broader final checks.

The affected complete isolated restore drill passed (1 test, 28.219s, exit 0) after fixing the chmod/chown ordering. It restores five archives and PostgreSQL into fresh volumes, checks all synthetic files/private modes and a database row, verifies temporary-container cleanup, then removes test resources. Added operator commands, key/trust requirements, failure recovery and cutover limitations to DEPLOYMENT.md; recorded evidence in VALIDATION.md. Static Ruff checks pass for the changed restore/test files. Final recovery suite and script-wide static checks follow; nightly scheduling/retention and actual deployed-application restore remain outstanding.


### Basic backup/restore slice validated — 2026-10-08

Final recovery suite passed all 15 tests in 22.043s (exit 0), including the complete isolated restore drill; Ruff and format checks pass for all 18 scripts and git diff --check is clean. Saving the basic backup/restore implementation and operating instructions in a local commit. No full-backend/frontend rerun was needed for these standalone recovery scripts. REVIEW.md remains untouched and excluded from the commit. Next finish the existing nightly scheduling/retention requirement, then move to the intended-host acceptance prerequisites; optional UI/collection expansion remains deferred. Existing dependency/network/live-provider blockers are unchanged and the full plan is not complete.

Basic backup/restore slice saved locally as `799a836`. No remote publication.


### Nightly backup and retention checkpoint — 2026-10-08

Added opt-in `backup.py --retain`: after a successful snapshot is published, keep the newest backup from seven distinct UTC dates and four distinct ISO weeks (overlap shares a snapshot). Incomplete, foreign-project, future-dated, unexpected-layout and non-private/symlink/hardlink candidates are excluded. A standalone retention preview never deletes. The backup lock now resides in the destination so separate checkouts sharing that destination cannot overlap. Added uninstalled systemd service/timer templates for 02:00 host-local time plus up to ten minutes jitter, with bounded shutdown time for writer recovery. No timer was installed/enabled and no real backup was pruned.

`systemd-analyze verify deploy/systemd/jobfinder-backup.service deploy/systemd/jobfinder-backup.timer` passed (exit 0), with unrelated pre-existing host unit PIDFile warnings. Calendar parsing showed the next two 02:00 local occurrences. Ruff import ordering was corrected. Initial six retention tests: five passed; deletion-count expectation failed (30 versus 31) because the fixture clock was later than actual time, correctly excluding a future-dated snapshot. Freeze the test clock and rerun; this is a test determinism issue, not a dependency or deployment blocker. Next finish operating instructions and final regression checks.


### Nightly backup tooling locally validated — 2026-10-08

`JOBFINDER_RECOVERY_TEST_DB_CONTAINER=jobfinder-test-db-1 python3 -m unittest discover -s scripts -p 'test_re*.py' -v` passed all 21 recovery/retention checks in 11.983s (exit 0), including the full disposable restore drill. Ruff/format pass for all 20 scripts and git diff --check passes. Documented installation, host-local timer timing, catch-up behavior, termination recovery, retention preview, exact seven-date/four-week semantics and the remaining need for periodic private-key restore verification. Saving this phase locally; no production pruning, timer installation, dependency retry or live API request occurred.

Next acceptance requires the intended Ubuntu environment (or resolution of this environment's existing dependency/network blockers). Asked the user whether to move the next session to that server or resolve this environment first. OpenRouter task model choices/key and explicit paid validation remain deferred, and source/device/deployed-recovery acceptance remains unproven. Do not replace this blocked acceptance work with optional UI or extraction expansion. The goal remains active; prior turn and this turn made verified implementation progress, so this is not a three-turn impasse audit.

Nightly backup/retention phase saved locally as `2e5a02b`. REVIEW.md remains untouched and untracked.


### Acceptance prerequisite check — 2026-10-08

Previous goal turn made progress: committed nightly backup/retention as 2e5a02b with 21 passing checks. Current read-only inspection confirms no deploy.env is present, the plan still requires intended-host network/ingress/source/device acceptance, and no user response selecting the host route or authorizing live models has arrived. The fetch-isolation gate remains disabled; dependency retry restrictions still apply. No live process is being awaited and no failed setup command was retried.

The immediate next step requires the user's environment choice already requested: move this checkout to the intended Ubuntu server for the next session, or resolve the current dependency/network blockers. Then supply deployment addresses and, for paid validation, task model choices/key/authorization. No optional features were added to substitute for this acceptance work. This is the first continuation at an actual acceptance impasse after the completed backup phase; keep the goal active and do not claim completion.

Acceptance impasse check 2: the previous continuation made no implementation progress and was not waiting on a live process. Fresh inspection again finds no deploy.env; no environment choice or changed authorization has arrived. The same intended-host/dependency-network prerequisite remains unresolved. No safe independent task advances the selected real-world acceptance milestone without substituting optional work. No setup retries or tests were run. Goal remains active pending the already-requested user input.

Acceptance impasse check 3: fresh inspection confirms deploy.env is still absent and no environment decision, network/dependency resolution or live-provider authorization has arrived. The previous turn was no progress, not a verified process wait. The same prerequisite has now blocked three consecutive continuations after the validated backup work. No meaningful independent work advances the selected acceptance milestone within current constraints. Marking the goal blocked, not complete. Resume when the user opens this project on the intended Ubuntu server or provides resolution/new instructions for this environment; live matching additionally requires model/key/paid-test authorization. Full PLAN.md scope and remaining acceptance gates are preserved.

### Deployment-agent continuation guide — 2026-10-08

Created FINISH_DEVELOPMENT_AND_VALIDATE.md at the owner's request, grounded in the current plan, context, progress, deployment files, provider implementation and operational scripts. It covers transfer, host intake, registry/lock portability, fresh regression checks, private deployment, remaining preset/browser implementation, real isolation tests, source/model/digest acceptance, operational restore/timer checks and final release evidence. Optional expansion remains deferred. Updated DECISIONS.md with the owner's initial @preset/job-finder testing direction; this does not replace OpenRouter with the development agent's local LLM.

Source inspection identified three concrete preset gaps: TaskConfig rejects the alias, endpoint capability checks require concrete model slugs, and response validation rejects a resolved concrete model when an alias is configured. The guide also calls out deploy/.env versus deploy.env inconsistency, the hard-disabled fetch gate/preflight assertion, existing requested/returned model fields to reuse, and the distinction between frontend test browsers and the missing Python renderer. Public official OpenRouter preset documentation was consulted; no authenticated provider call was made.

Documentation verification passed: local Markdown links, referenced repository paths, final newlines/trailing whitespace, balanced fences, and bash -n on shell examples without executing them. Git diff whitespace checks passed. No application code, dependencies, credentials, containers, host settings, existing REVIEW.md or runtime state was changed. Preserved prior uncommitted progress updates. Next action: transfer the complete handoff to the intended host, follow section 4 intake, and execute the phases there; the deployment/preset/live gates are not claimed complete.

Guide and preset decision saved locally in `4e0c624`; no push. The owner subsequently requested committing the remaining changes for transfer. PROGRESS.md (including the preserved earlier checkpoints) and REVIEW.md are included in the follow-up documentation commit, so the complete handoff can be transferred through Git. The owner will push; no remote operation is authorized or performed here.


### Historical local live API validation attempt — 2026-10-09 (subsequently canceled)

User assigned DEPLOYMENT_API_VALIDATION.md; this supersedes host-first sequencing for the bounded synthetic API exercise only. Baseline b58706d; worktree initially clean. Authorized total remains US$1 or 60 inference attempts across all phases/restarts. Both selected model listings were found in official OpenRouter public documentation. User additionally permits medium reasoning for Luna testing; use it only where endpoint support is verified. Installed HTTPX/dotenv/psycopg/pytest are available. Metadata-only checks confirm .env/.secrets/.data paths are ignored; test PostgreSQL is healthy and the host listener is exclusively 127.0.0.1:55439. No secret value or real CV was read.

Live transport blocker: a single unauthenticated HTTPX GET to `https://openrouter.ai/api/v1/models/openai/gpt-6-luna/endpoints` using the installed backend interpreter, timeout 20s and redirects disabled failed with `httpx.ConnectError`; sanitized exception inspection confirms certificate verification failure. The diagnostic process exited 2. No inference POST or authenticated request occurred (known spend $0, held $0, inference attempts 0; metadata GET attempts 1). Stop live work on this path per the plan; no retry, alternative trust/proxy, or dependency operation attempted. Requested environment trust resolution/new instructions. Official Jev guide and model listing are readable through public research, but the linked Decisions API reference could not be retrieved; mandatory privacy controls remain unverified. Continue independent offline launcher/budget work, not guessed live contracts.


### Local live validation canceled; deployment handoff consolidated — 2026-10-09

At the owner's request, retired the standalone local plan and moved its useful technical steps to DEPLOYMENT_API_VALIDATION.md as a deployment-only companion. Preserved the pre-existing uncommitted TLS diagnostic and medium-reasoning preference. Updated active guidance, parent section 8, model/budget prerequisites, acceptance matrix and continuation prompt; removed the obsolete preset implementation prerequisite. No source implementation, dependency operation, secret read, model call or runtime change occurred. The original development database and private files were not removed. Remote master was inspected read-only and is 8073fb2, an ancestor of the local branch, so this documentation commit can use a normal push; no history rewrite or push was performed.
