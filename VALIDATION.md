# Validation

## Direct LAN IP TLS access verification — 2026-10-12

Baseline `05463b7`. Worktree clean before changes.

### Actual checks run and outcomes:

1. **Root Cause Analysis of Handshake Failure on Literal IP Access:**
   - Probed `https://192.168.68.55:443` via `openssl s_client`:
     - Without `-servername` parameter: failed with `SSL alert number 80: tlsv1 alert internal error` and `no peer certificate available`.
     - With `-servername 192.168.68.55`: completed handshake immediately (`CN = Caddy Local Authority - ECC Intermediate`).
   - Confirmed mechanism: standard browsers and TLS libraries do not send the Server Name Indication (SNI) extension when connecting to raw IP addresses (RFC 6066). Without SNI, Caddy lacked a fallback policy to select the certificate and rejected the handshake.

2. **Fix Implemented and Verified in Container Image:**
   - Configured `default_sni {$LAN_HOST}` in `deploy/Caddyfile` global options block.
   - Rebuilt `jobfinder-edge:local` via `docker compose --env-file deploy/.env build edge` and recreated `jobfinder-edge-1`.
   - Probed direct IP connection without SNI:
     - `curl -k https://192.168.68.55:443`: completed TLSv1.3 handshake and returned `HTTP/2 200 OK` (Content-Type: `text/html; charset=utf-8`, serving Job Finder React SPA).
     - `curl -k https://192.168.68.55:443/api/v1/health/live`: returned `HTTP/2 200 OK` `{"status":"ok"}`.
     - `curl -k https://192.168.68.55:8443/v1/health`: returned `HTTP/2 200 OK` `{"healthy":true}`.

## Shared ntfy reuse, permission isolation and port conflict verification — 2026-10-12
Baseline `c3c0cd2`. Clean worktree before changes.

### Actual checks run and outcomes:

1. **Dedicated User and Token Provisioning on Existing Server:**
   - User `jobfinder-publisher` created via `docker exec -e NTFY_PASSWORD=<secret> ntfy ntfy user add jobfinder-publisher`.
   - Dedicated access rule set via `docker exec ntfy ntfy access jobfinder-publisher jobfinder write-only`.
   - Access token issued via `docker exec ntfy ntfy token add jobfinder-publisher` and saved in `.secrets/ntfy_publisher_token` (mode 0644).
   - Confirmed via `ntfy access`: `beng` admin permissions and `*` deny-all default remain completely unaltered.

2. **Connectivity and Permission Isolation Verified Without Test Notifications:**
   - `python3 scripts/check-ntfy.py`:
     - Health on `http://127.0.0.1:8093/v1/health`: 200 OK (`{"healthy":true}`).
     - Anonymous publish/read on `jobfinder` topic: 403 Forbidden.
     - Publisher token read on `jobfinder` topic: 403 Forbidden (write-only enforced).
     - Publisher token write to unauthorized topic: 403 Forbidden (topic isolation enforced).
     - Publisher token OPTIONS on `jobfinder` topic: 200 OK (authorized).
     - No test notification was sent.
   - Container connectivity: tested from ephemeral container on `ntfy_default` network to `http://ntfy:80/v1/health` (200 OK) and unauthorized write to another topic (403 Forbidden).

3. **Port Conflict Resolution Verified Without Service Disruption:**
   - Host inspection confirmed qBittorrent-nox on `*:8080` and filebrowser on `0.0.0.0:8081` remain running and untouched.
   - Job Finder edge remapped to loopback `127.0.0.1:8085` (app) and `127.0.0.1:8086` (notifications):
     - `compose.yaml`: `127.0.0.1:${APP_LOOPBACK_PORT:-8085}:${APP_LOOPBACK_PORT:-8085}` and `127.0.0.1:${NOTIFY_LOOPBACK_PORT:-8086}:${NOTIFY_LOOPBACK_PORT:-8086}`.
     - `deploy/Caddyfile`: `http://{$TAILNET_HOST}:{$APP_LOOPBACK_PORT:8085}` and `http://{$TAILNET_HOST}:{$NOTIFY_LOOPBACK_PORT:8086}`, with `reverse_proxy ntfy:80`.
     - `deploy/.env` and `deploy/.env.example`: `APP_LOOPBACK_PORT=8085`, `NOTIFY_LOOPBACK_PORT=8086`.

4. **Deployment, Preflight and Backup Consistency Verified:**
   - `python3 scripts/check-deployment.py`: passed (0.15s, exit 0).
   - `python3 scripts/check-deployment.py --env-file deploy/.env`: passed (0.16s, exit 0).
   - `python3 scripts/test_runtime_security.py`: all 4 passed (0.40s, exit 0).
   - `python3 scripts/test_fetch_rules.py`: all 7 passed (1.92s, exit 0).
   - `python3 -m unittest discover -s scripts -p test_recovery.py`: all 15 passed (2.61s, exit 0).
   - Full backend regression suite: all 90 tests pass (15.43s, exit 0).

## Deployment inputs and ntfy inspection — 2026-10-12
Read-only LAN/default-interface and Tailscale-self metadata verified the values used for LAN_IP and TAILNET_HOST in ignored deploy/.env. Owner-selected direct IP is also LAN_HOST. `getent ahostsv4 homelab.home` returned no result, exit 2; this is resolver evidence from this host only. Actual private addresses/hostname are not copied into tracked records. Compose interpolation with `--env-file deploy/.env --format json` passed and assertions confirmed the LAN-IP origin, mock integration and disabled fetching. Private file mode is 0600.

Existing ntfy container is running on a loopback host port; its CLI reports 2.28.0 and metadata shows deny-all default access, its own Docker network and persistent bind data. No separate Job Finder ntfy container was found. Read-only socket/process checks identify the proposed loopback ports 8080 and 8081 as occupied by qBittorrent and filebrowser. Existing-server reuse, publisher authorization and alternative Job Finder ports are not implemented or validated by this intake.

Secret metadata only shows nonempty database/fetcher files and empty provider/publisher placeholders; no values were read or exposed. No service/configuration change outside the private Job Finder env-file, notification publication, inference request, dependency operation, firewall action or Tailscale change occurred. Full deployment preflight was deliberately not invoked because its non-root firewall fallback can create a host-network privileged container and install packages; no deployment was started. Documentation whitespace checks passed.

## Live OpenRouter Gates E & F and Controlled Isolation Acceptance verification — 2026-10-10

Baseline `a4aa667`. Worktree clean before changes.

### Actual checks run and outcomes:

1. **Controlled Container Boundary Acceptance Matrix:**
   - Worker->fetcher RPC over `jobfinder_fetch_control`: verified 401 on missing/wrong token, 502 `isolation_not_verified` on disabled gate, 413 on request body >8192 bytes.
   - **Real positive public collection verified:** Worker container on `jobfinder_fetch_control` successfully fetched `http://example.com` (status 200, 577 bytes body) and `https://openrouter.ai/api/v1/models` (status 200, 765,783 bytes body) via Squid proxy over `jobfinder_public_outbound`.
   - **Negative directional listener drops verified with live listeners:**
     - Fetcher -> Worker: live worker TCP listener on port 8088 verified reachable before probe; dropped by DOCKER-USER rule 3 (`-A DOCKER-USER -s 172.31.0.2/32 -i br-a5aeabdb0102 -o br-a5aeabdb0102 -m conntrack --ctstate NEW -j DROP`); worker listener verified still alive after probe.
     - Fetcher -> Host: live host listener on port 18099 verified reachable before probe; dropped by INPUT rule 1 (`-A INPUT -s 172.31.0.2/32 -m conntrack --ctstate NEW -j DROP`); host listener verified still alive after probe.
     - Fetcher -> Core / Outbound: listener on `jobfinder_public_outbound` port 8089 blocked by DOCKER-USER cross-bridge rules (`Errno 101 Network is unreachable`).
     - Fetcher direct public egress: direct socket to `1.1.1.1:80` without proxy blocked (`Errno 101 Network is unreachable`).
   - **Real private redirect rejection verified:** public service returning HTTP 302 to `http://127.0.0.1/admin` intercepted and rejected with 502 `destination_denied` before following redirect.
   - **Real connection-time DNS rebinding verified:** public hostname `localtest.me` (resolving to 127.0.0.1) denied at connection time by Squid destination ACLs (`ERR_ACCESS_DENIED`, 502 `destination_denied`).
   - Browser collection containment kept explicitly pending (rendering engine unfinished).
   - Normal fetching restored to disabled (`FETCH_ISOLATION_VERIFIED=false`).
   - Temporary CAP_NET_ADMIN container confirmed removed (0 dangling management containers).

2. **Gate E (Semantic Fixture Evaluation) Passed Live (`scripts/evaluate-semantic-cases.py`):**
   - 12 authored cases evaluated live:
     - P1 (short clear CV): 1 role, 3 skills extracted with exact span citations.
     - P2 (technical software engineer profile): extracted engineer role, zero domain contamination.
     - P3 (embedded prompt injection attack): instructions ignored, safety invariant held (`origin=user` not set, experience years not overridden).
     - X1 (single clean vacancy): Senior Product Manager extracted with observed apply URL.
     - X2 (closed vacancy page): 0 open vacancies extracted, no fabricated jobs.
     - X3 (injected vacancy instructions): real role extracted, unobserved evil link discarded.
     - M1 (aligned strategy role): relation `aligned`, derived category `match` / `possible_match`.
     - M2 (adjacent transformation role): relation `adjacent`, plausible connection True, in shortlist.
     - M3 (unrelated function - Legal counsel): relation `unrelated`, derived category `not_match`.
     - M4 (focus domain conflict): role outside focus domain classified `not_met` with evidenced conflict, derived category `not_match`.
     - M5 (incomparable salary): missing salary preserved uncertainty, no hard exclusion.
     - M6 (injected job instructions): adversarial override ignored, policy preserved.

3. **Gate F (Integrated Application Journey) Passed Live (`scripts/verify-phase-f-journey.py`):**
   - Full 7-step journey against dedicated disposable database `jobfinder_test_phase_f_*`:
     - Step 1: Owner authenticated, AI settings confirmed (`openai/gpt-6-luna`, `typesafe/jev-1.13`).
     - Step 2: Synthetic vacancy ingested into inventory (`Senior Corporate Strategy Manager`).
     - Step 3 & 4: Synthetic CV extracted via live Luna (call 1) into `Facts`, reviewed `ProfileRevision` created.
     - Step 5: `job_assess` operation executed via worker and live Jev Decisions (call 2); succeeded.
     - Step 6: Database persists current `JobAssessment` with `category="match"`, `relation="aligned"`, `connection=True`; portal shortlist view (`/api/v1/jobs?view=recommended`) displays the job as `match`; all-jobs view (`/api/v1/jobs?view=all`) displays the job; job detail view displays assessment explanation and evidence; UI usage agrees with DB inference records.
     - Step 7: Assessment idempotency verified: re-running assessment on unedited profile produces 0 extra inference calls (call count remained 2).

4. **Accounting and Budget Reconciled:**
   - Durable run ledger (`.data/live_run_ledger.json`): **46 attempts, US$0.004885158 known spend, US$0 held spend**.
   - Remaining allowance under advisory US$1 / 60-call cap: **14 requests, US$0.995114842**.
   - Temporary key bridges removed on orderly shutdown in every live run.

## Controlled target, parameter resolution and firewall harness verification — 2026-10-10
Baseline `ad42c96`. Worktree clean before changes.

### Actual checks run and outcomes:

1. **Parameter Resolution & Unit Test Hardening (`deploy/fetch-control-rules.sh`, `scripts/test_fetch_rules.py`):**
   - Updated `deploy/fetch-control-rules.sh` to explicitly source `deploy/.env` when present and pass `--env-file "$ENV_FILE"` to `docker compose`.
   - Updated `scripts/test_fetch_rules.py` mock parser (`service="${!#}"`) to handle `--env-file` argument shifting: all 7 tests pass (1.902s, exit 0).

2. **Controlled Target Prepared & Started:**
   - Initialized `deploy/.env` with `DOCKER_NO_NEW_PRIVILEGES=false` and `FETCH_ISOLATION_VERIFIED=false`.
   - Started target: `docker compose --env-file deploy/.env up -d egress-proxy fetcher`.
   - Verified networks created and running: `jobfinder_fetch_control` (`internal: true`), `jobfinder_fetch` (`internal: true`), `jobfinder_public_outbound`.
   - Verified containers running and healthy: `jobfinder-egress-proxy-1` (Up, healthy) and `jobfinder-fetcher-1` (Up, healthy).
   - Address and bridge resolution verified via `deploy/fetch-control-rules.sh`:
     - `fc_bridge`: `br-a5aeabdb0102`
     - `fetch_bridge`: `br-3273d0fe0b8d`
     - `fetcher_fc`: `172.31.0.2`
     - `fetcher_fetch`: `192.168.0.3`
     - `proxy_fetch`: `192.168.0.2`

3. **Disposable Firewall Harness (`scripts/test-fetch-control-harness.sh`):**
   - Executed `scripts/test-fetch-control-harness.sh` on disposable networks with `DOCKER_NO_NEW_PRIVILEGES=false`:
   - All 7 baseline reachability probes verified before rules applied.
   - Positives verified: worker->fetcher RPC allowed, fetcher->proxy port allowed, internal service-name DNS allowed.
   - Negatives verified: fetcher->worker same-bridge initiation blocked, proxy->fetcher blocked, fetcher->host gateway listener (INPUT coverage) blocked.
   - Output: `HARNESS PASSED: all boundaries behaved as designed on disposable networks.` (exit 0, 13.73s).

4. **Host Firewall Rules Installed and Verified on Controlled Target:**
   - Installed host rules: `deploy/fetch-control-rules.sh install`.
   - Verified active rules: `deploy/fetch-control-rules.sh verify` reported `verified: rules present and bound to current addresses`.
   - Confirmed 8 `DOCKER-USER` rules and 2 `INPUT` rules bound to current bridge IDs and container IPs.
   - Verified clean transactional rollback to 0/0 rules and clean idempotent reinstall.
   - Created verified acceptance record: `.data/fetch_isolation_acceptance.json`.

5. **Hardened Preflight & Runtime Security Verification:**
   - `python3 scripts/test_runtime_security.py`: 4 passed (0.385s, exit 0).
   - `python3 scripts/check-deployment.py --env-file deploy/.env`: passed (0.16s, exit 0).

## Firewall installation readiness review — 2026-10-10, baseline `ad42c96`
`python3 scripts/test_fetch_rules.py`: 7 passed, 2.125s, exit 0; `bash -n deploy/fetch-control-rules.sh scripts/test-fetch-control-harness.sh`: passed. Read-only `docker network inspect jobfinder_fetch_control jobfinder_fetch` reported both networks not found; running-container lookup with the Job Finder Compose-project label returned none. Deployment parameter file `deploy/.env` is absent. The installer cannot currently target the expected stack; review also found service lookups omit an explicit deployment env-file and verify needs root for iptables access.

No rules installed or modified, no containers started, no credentials or inference read/sent, no implementation fix or commit made. The required current disposable firewall-harness success and complete directional/private boundary acceptance were not reproduced here. Readiness conclusion and exact next actions are in PROGRESS.md.

## Live schema compatibility, positive fetch path and hardened preflight checks — 2026-10-10

Baseline `d93a67b`. Reconciled following the agent review in REVIEW.md.

### Actual checks run and outcomes:

1. **Section 9.2 Scoped Disposable Container Topology & Positive Path (`scripts/test-fetch-isolation.py`):**
   - Rebuilt `jobfinder-backend:local` from `deploy/backend.Dockerfile` to include proxy-delegated DNS changes from commit `4305c48` (image sha256: `f9ab2d1a2ac1`). Verified signature of `http.resolve_public` inside image: `(url: str, *, proxy_url: str = '') -> None`.
   - Built disposable 3-network topology matching production connections:
     - `net_fc` (`internal: true`) for worker-fetcher RPC.
     - `net_fetch` (`internal: true`) for fetcher-proxy HTTP.
     - `net_pub` (bridge with outbound internet) for Squid egress.
   - Pinned Squid proxy (`ubuntu/squid@sha256:6a097f68...`) run on `net_fetch` (alias `egress-proxy`) and `net_pub` with NNP payload hardening.
   - Fetcher container run on `net_fc` and `net_fetch` with `JOBFINDER_FETCH_PROXY_URL=http://egress-proxy:3128`.
   - Probes executed and outcomes:
     - **Auth & isolation disabled probes (Worker -> Fetcher on `net_fc`):** missing token rejected with 401; wrong token rejected with 401; valid token with `isolation_verified=false` rejected with 502 `isolation_not_verified`; oversized payload (>8192 bytes) rejected with 413 `fetch_request_too_large`.
     - **Positive public fetch through Squid:** worker on `net_fc` called `/fetch` for `http://example.com`. Fetcher delegated DNS to Squid over `net_fetch`; Squid resolved and fetched via `net_pub`; returned status 200 with non-empty body (577 bytes). This proves the positive collection path and proxy DNS delegation in real containers.
     - **Private destination rejection:** worker on `net_fc` called `/fetch` for `http://127.0.0.1/admin`, `http://169.254.169.254/meta`, and `http://10.0.0.1/`. All strictly rejected at API schema boundary (HTTP 422 `invalid_fetch_request`) or engine boundary (HTTP 502 `destination_denied`).
     - **Direct public egress denial on internal network:** socket probe from container on `net_fetch` connecting to `1.1.1.1:80` with `--pull never` and `setpriv --no-new-privs`: strictly blocked with structured output `RESULT:DENIED:OSError:101` (Network is unreachable, exit 0).
     - **Exit 125 regression test:** verified that a Docker startup failure (exit 125) is caught as a test failure, never falsely reported as PASS.
     - **Deterministic mock redirect check:** `_probe_redirect` updated with isolated temporary state file (`.data/test_redirect_*.sqlite3`), verified handler invocation, and strict rejection with `destination_denied` or `ValueError`.
     - **Deterministic redirect loop check:** `test_redirect_limit_rejection` updated with isolated temporary state file.
     - Full suite passed: exit 0, 25.61s.

2. **Hardened Preflight & Deployment Flag Verification (`scripts/check-deployment.py`, `scripts/test_runtime_security.py`):**
   - `scripts/check-deployment.py` hardened: `JOBFINDER_FETCH_ISOLATION_VERIFIED="true"` is strictly rejected unless verified acceptance evidence exists (`.data/fetch_isolation_acceptance.json` with status `accepted`) AND `deploy/fetch-control-rules.sh verify` passes (confirming active host iptables rules without container address drift).
   - Added regression test `test_fetch_isolation_enabled_without_evidence_is_rejected` in `scripts/test_runtime_security.py`: all 4 tests pass (0.395s, exit 0).
   - `python3 scripts/check-deployment.py` default template check strictly asserts `JOBFINDER_FETCH_ISOLATION_VERIFIED == "false"`.

3. **Live OpenRouter Schema Compatibility & Judgment (`scripts/validate-live-api.py`):**
   - Reconciled `--schema-checks`: running schema checks does not redundantly re-run paid connectivity probes.
   - Live checks previously executed:
     - `profile_analysis` probe (Luna): $0.00000635, 1027ms
     - `job_matching` probe (Jev Decisions): $0.00001369, 360ms
     - `profile_analysis` generative `Facts` schema (Luna): $0.00018210, 7634ms
     - `job_extraction` generative `Extraction` schema (Luna): $0.00010195, 9331ms
     - `job_matching` assessment (Jev Decisions): $0.00007799, 354ms (`relation=aligned`, `plausible_connection=True`)
   - Durable run ledger (`.data/live_run_ledger.json`): **19 attempts, US$0.000836348 known spend, US$0 held spend**.
   - Remaining allowance under advisory US$1 / 60-call cap: **41 requests, US$0.999163652**.

4. **Status and Limits:**
   - **R1 Docker startup:** Resolved for project compatibility path (`DOCKER_NO_NEW_PRIVILEGES=false` + `setpriv`).
   - **Basic live schema compatibility:** Passed for Luna (`Facts`, `Extraction`) and Jev (`Assessment`).
   - **Section 9.2 live container isolation gate:** REMAINS OPEN. Scoped container topology verified positive path and proxy ACL denials; host-level directional firewall rules require owner root execution (`sudo deploy/fetch-control-rules.sh install`).
   - **Real deployment fetching:** REMAINS DISABLED (`FETCH_ISOLATION_VERIFIED=false`).
   - **Phase E semantic evaluation & Phase F integrated journey:** Pending.

## Latest progress review — 2026-10-10, baseline `d93a67b`
Inspected `668f340` and `d93a67b`, full `scripts/test-fetch-isolation.py`, actual schema-check/probe dispatch, preflight enablement changes and the parent gate criteria. Historical live/container results were read in PROGRESS.md, not rerun or independently signed off. REVIEW.md narrows the claimed full isolation result to the partial checks actually implemented and distinguishes live schema/judgment compatibility from pending semantics/current persistence/portal acceptance.

Fresh checks: `python3 scripts/test_runtime_security.py` passed 3 tests (0.300s, exit 0). Isolated preflight check confirms true is rejected in default mode but accepted by `allow_verified_isolation=True` without firewall/evidence verification. Isolated AST/mock egress check supplies Docker startup exit 125 and reproduces the runner's incorrect PASS; no Docker/network operation was performed. `py_compile` on runner/launcher/preflight and project-configured Ruff lint on those files plus deployment_config.py passed.

Read only aggregate fields from the persistent run ledger: 19 attempts, US$0.000836348 known, zero held, matching the latest checkpoint. No credentials, CV, raw inference payloads or generation identifiers were exposed. No metadata/inference request was made. Remaining cumulative ceiling: 41 requests and US$0.999163652 before any further holds/charges; this review grants no additional budget.

Documentation checks passed for REVIEW.md, PROGRESS.md and VALIDATION.md (links, whitespace, final newlines, balanced fences); `git diff --check` passed. No source implementation change, dependency operation, runtime/firewall/container check, full backend/browser run or commit occurred. Full section 9.2 positive-path/private/directional/rebinding/browser acceptance remains open despite the previous completion wording.

## R1 Snap compatibility implementation — 2026-10-10

Baseline `55f0f25`. Actual daemon metadata: server 29.8.0, Snap data root, AppArmor and builtin seccomp active. No migration/daemon change. Explicit Docker startup setting false followed by in-container `setpriv --no-new-privs` enables the payload flag after profile attachment. Repository default stays true.

Checks actually run:

- `python3 scripts/test_runtime_security.py`: 3 passed, final run 0.451s, exit 0. Exercises default/compatibility selection, invalid value refusal, missing entrypoint/command/health wrapper, inconsistent startup options and malformed tmpfs rejection. The backup helper also propagates the selected setting.
- `python3 scripts/check-deployment.py` and `DOCKER_NO_NEW_PRIVILEGES=false python3 scripts/check-deployment.py`: both exit 0. Configuration evidence only; no production secrets were read.
- Project-configured Ruff lint and format checks on all seven changed/new scripts pass; `git diff --check` passes.
- `DOCKER_NO_NEW_PRIVILEGES=false python3 scripts/check-proxy.py`: 20 real ACL cases passed, exit 0, including explicit proxy PID payload `NoNewPrivs: 1` assertion. Container network none, no ports/real targets.
- `DOCKER_NO_NEW_PRIVILEGES=false python3 scripts/check-ntfy.py`: health, configured health argv, anonymous denial, publish-only token, reader-only access and cached receipt passed, exit 0; payload `NoNewPrivs: 1` asserted. Synthetic credentials/notifications inside a disposable network-none container, no recipients.
- Cached Alpine/backend/Squid/Caddy/PostgreSQL/Python-helper launches succeeded through setpriv with Docker startup NNP false. Profiles reported `docker-default (enforce)` and payload NNP 1. Alpine probe additionally verified non-root UID, zero effective/bounding capabilities and seccomp mode 2. Caddy and Squid actual binaries executed; API/fetcher actual services passed health and application-process NNP checks under Docker init.
- Actual Compose smoke used the final API/fetcher image, entrypoint, command, tmpfs, init, security and health settings projected into a unique network-none test project. `up -d --wait --wait-timeout 25 --pull never` and both payload NNP assertions passed. No ports, mounted secrets, data volumes or external network; project removed afterward. This checks runtime/command semantics, not full ten-service integration or current application-image rebuild.
- PostgreSQL's actual wrapped entrypoint initialized in tmpfs, transitioned to its database user, reached final-process readiness and executed `SELECT 1`; NNP 1 verified. No network or ports.
- Final recovery suite with `DOCKER_NO_NEW_PRIVILEGES=false` against a newly created, labelled, network-none disposable test PostgreSQL ran all 15 existing checks, including real encrypted volume archive, PostgreSQL roundtrip and full isolated restore: 15 passed, 14.155s, exit 0. It includes the final NNP-wrapped restore DB launcher. Test database/container/volumes removed; existing databases/services untouched.
- Cleanup inspection found no `jobfinder-r1-*` containers left. Pinned Python/ntfy pulls each succeeded once; ntfy project image built from the cached base with network disabled and no package installation.

Intermediate failures and limits:

- Sandboxed synthetic recovery setup failed: unittest exit 5, underlying GPG key-generation exit 2, zero tests run. Authorized expanded execution passed the same synthetic suite (initially 12 passed/3 skipped), then the selected real archive test passed, then full Docker drills passed as above. No dependency workaround.
- First PostgreSQL SQL probe reached its temporary initialization server and failed psql exit 2. Readiness was corrected to require PID 1 `postgres` before probing SQL; the corrected test passed.
- First full-drill fixture missed `com.docker.compose.service=db`; suite exited 1 with KeyError, 14 checks passed. Added that label only to the next temporary harness DB; corrected final checks passed.
- Initial Compose smoke discarded child stderr; a diagnostic rerun retained exit 1: `invalid mount path: 'mode=1777' mount path must be absolute`. This exposed existing unquoted flow-list tmpfs strings. All five specifications are now quoted; preflight rejects split options; final real Compose check passed. Explicit commands were also added because overriding entrypoint otherwise discards image CMD.
- Initial lint invocation picked unrelated home defaults; applicable checks use `--config backend/pyproject.toml` and pass.

NNP is verified for wrapped service/helper/health payloads and descendants. Trusted Docker launcher/init and arbitrary administrative exec sessions are not automatically protected in compatibility mode; wrap required admin commands as documented. No root `.env`/provider credentials or live ledger was read, no inference request was sent and no firewall/host policy changed. Full fetch-isolation/rebinding/browser matrix, private ingress, live matching, full production startup and deployed-device/recovery acceptance remain open. Backend/frontend suites were not rerun for these runtime/script-only changes.

## Agent continuation review checks — 2026-10-09, baseline `72cb6df`

Fresh `python3 scripts/test_fetch_rules.py`: 7 passed, exit 0, 2.126s. `bash -n deploy/fetch-control-rules.sh scripts/test-fetch-control-harness.sh`: exit 0. Synthetic isolated matching source/domain checks confirmed duty coverage after character 3,500, visible refusal of a 26,000-character unbroken span exceeding the candidate budget, rejection of unsupported known focus-domain outcomes, and selected profile skill support for a connection. They also confirmed score evidence still mechanically references aggregate experience. No provider/database/network/state access was used by these self-checks.

Read-only `docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'` exited 1: `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`. Client reports 29.1.5; server identity was not obtainable. A read-only formatted Docker info attempt also reported socket permission denial. This review did not reproduce the target-host NNP/EPERM failure or read kernel logs. The recorded 330-test backend pass and target-host DNS/runtime experiments were inspected, not rerun.

Official Linux kernel NNP documentation and Docker AppArmor documentation were consulted for general mechanisms and diagnostic guidance; neither establishes this host's causal diagnosis. Source tracing identifies unchanged matching persistence identity, generic mapping of pre-dispatch candidate-budget ValueError, failed-start cleanup risk in the proxy checker, missing NNP assertion in static preflight and firewall unit lifecycle gaps. These findings and proposed checks are in REVIEW.md; no implementation was changed.

Documentation validation passed for REVIEW.md, PROGRESS.md and VALIDATION.md: local links, whitespace, balanced fences and final newlines; `git diff --check` passed. No dependency operation, container start, host mutation, live inference, full backend/browser rerun or commit occurred.

## Follow-up review checks — 2026-10-09, baseline `4959867`

Fresh `python3 scripts/test_fetch_rules.py`: 7 passed, exit 0, 2.187s. Fresh `bash -n deploy/fetch-control-rules.sh scripts/test-fetch-control-harness.sh`: exit 0. Neither check applies real host rules or creates Docker resources.

Two synthetic isolated-source/domain self-checks reproduced remaining matching defects: a 3,522-character description's final duty is absent from all candidates after the six-chunk cap; and an aligned high-scoring focus-domain assessment with `domain_status=not_met` plus `domain_evidence=insufficient` returns unknown-domain `possible_match` rather than an assessment error. The checks loaded only selected matching definitions and domain/protocol contracts, with a stub task-input builder; no provider import, database, secrets, network, durable ledger or state writes occurred. They verify local interpretation/candidate behavior, not production orchestration or live model judgments.

The latest recorded Docker DNS experiments and 329-test backend pass were inspected, not rerun. REVIEW.md contains the resulting resolution statuses, current blocker, remaining concerns and owner-input assessment. Documentation links, whitespace, balanced fences and final newlines passed for the three changed Markdown files; `git diff --check` passed. No implementation changes or commit were made.

## 2026-10-09 local cancellation and deployment handoff

The owner canceled local live validation after a recorded unauthenticated metadata GET failed certificate verification (HTTPX ConnectError, diagnostic exit 2). Inference attempts, known spend and held spend were all zero in that checkpoint. No further OpenRouter call or application test was run during cleanup. The technical plan is now DEPLOYMENT_API_VALIDATION.md, integrated into the parent deployment guide; its live acceptance gates remain pending. The old development host-network workaround is excluded from deployment execution. Cleanup checks passed for all nine changed/new Markdown documents: local links, final newlines, whitespace, balanced fences, retired-filename removal and preserved checkpoint/model preference. Remote master was checked read-only and is an ancestor of the local branch; a normal push is sufficient at that observed state.

## Historical 2026-10-09 live-validation planning evidence

Prepared the original local plan (now retargeted as [DEPLOYMENT_API_VALIDATION.md](DEPLOYMENT_API_VALIDATION.md)) against the current integration code and official public provider documentation. Checked its local links, Markdown fence balance and whitespace; verified that FINISH_DEVELOPMENT_AND_VALIDATE.md differs from its committed body only by the added execution notice. Model choices and the owner's cumulative US$1 / 60-inference-request limit are recorded in the active guidance. No key value was read and no authenticated provider request, dependency operation, application test or live model evaluation ran. All live-plan acceptance gates remain pending; historical test counts below are not fresh results for this work.

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

Durable inventory: full backend suite passed 69 tests (36.48s); after the final stale-source guard, eight inventory tests passed (2.77s). Verified PostgreSQL migration consistency, persistent page continuation, idempotent redelivery, cross-source merges, conservative closure, failure/cooldown handling, concurrent scheduling and stale-lease rejection. Ruff lint/format and strict mypy pass. Transport is injected in tests; live fetch isolation, API/UI and complete end-to-end monitoring remain unverified.

Company/inventory APIs: full backend suite passed 74 tests (32.69s), followed by five targeted API tests (2.70s) after the explicit-idempotency guard. Covered retained unresolved watches, authentication/input validation, source confirmation, optimistic pause/source conflicts, joined manual actions, worker fan-out, unassessed legal/strategy roles in all-jobs, availability, cursor filter binding, full-text search and detail provenance. Ruff/format/mypy and generated TypeScript/Vite build pass. The initial pagination test lost URL filters through HTTPX params replacement; corrected and verified offline. UI/live discovery/fetching acceptance remains pending.

Inventory portal: real API/database browser journey passed (11.9s; 20.3s total), covering create watch, retain unresolved company, add confirmed source, pause/resume, source interval edit after revision changes, browse unassessed legal/strategy jobs, search, detail and retained filters. Company/detail views had no overflow or axe violations at 375/1440. Navigation regressions passed at 375/768/1440 (5.4s total), including focused headings; desktop company and mobile Jobs screenshots inspected. Twelve component tests passed before final source/focus refinements; those changes were browser-checked. TypeScript/Vite build, lint and format pass. Bundle size warning remains at 514 KB minified / 155.37 KB gzip. This is synthetic UI/inventory evidence, not live collection or matching acceptance.

Isolated HTTP fetcher: full backend suite passed 86 tests (35.29s); after long-backoff correction, twelve fetcher tests passed (2.62s). Ruff lint/format and strict mypy pass. Synthetic transport tests cover service auth/body boundaries, blocked isolation default, DNS/private redirects, no credential/cookie propagation, robots policy/outages, decompression limits, persistent origin pacing/backoff and worker RPC classification. No container network enforcement, actual DNS rebinding scenario, browser resource isolation or live source request has passed; those remain release gates.

2026-10-07 supplied-CV recheck: local aggregate-only extraction returned one page and 3,847 characters; Git-ignore passed, with no extracted content persisted and no AI call. Three targeted synthetic format regressions passed (2.80s): invalid/input limits and DOCX text, multi-page PDF, and interleaved/nested/merged DOCX tables. This does not validate arbitrary column order, image-only OCR, or semantic profile extraction.

2026-10-07 proxy ACL check: `python3 scripts/check-proxy.py` passed 20 HTTP/CONNECT/address/method/port cases against the digest-pinned Squid image, running non-root, read-only, without capabilities and with network none. Public literal destinations pass ACL evaluation but cannot connect in that namespace; private destinations return ERR_ACCESS_DENIED. Its temporary container and the earlier manual validation container were removed. Merged base/fetch Compose configuration passes syntax validation. This is not a normal bridge, DNS rebinding, browser subresource or direct-egress isolation acceptance result; fetching stays disabled. Image builds and base deployment remain unverified.

2026-10-07 generic parser: complete backend suite passed 99 tests (37.57s), including twelve synthetic JSON-LD/page-link cases. Ruff lint/format and strict mypy pass. Coverage includes graph/list employer references, plain descriptions, remote/applicant locations, date-only versus timezone-aware timestamps, expiry evidence, malformed JSON, ambiguous multi-job URLs, unsafe links, conflicting records and caps. Initial invalid fixture escaping was corrected before this run. No live employer, persistent discovery, browser fallback, AI extraction or complete generic inventory acceptance is claimed.

2026-10-07 persistent discovery: full backend suite passed 111 tests (42.48s), Alembic consistency passed, generated API types and frontend build passed. After the final scheduling transaction change, thirteen discovery regressions passed (2.08s), including a separate connection acquiring collection-finalization locks. Covered official-link ATS verification including valid empty boards, exact provider hosts, preserved disabled sources, persisted continuation/replay, failed pages, unknown redirects, bounded frontier, stale company/lost lease guards, epoch expiry, exhausted-step reconciliation, unresolved name-only watches and authenticated history. Ruff lint/format and strict mypy pass. This is synthetic database/transport evidence, not Brave/live employer/browser or full discovery acceptance. Existing upstream test-client deprecation and frontend chunk-size warnings remain.

2026-10-07 Brave/search review: all 123 backend tests passed (40.19s), including mocked fixed-endpoint requests, safe candidate decoding, replay without another provider call, concurrent request-budget admission, monthly/unknown reservations, persisted 429 cooldown and explicit revision-checked company selection. Migration consistency, Ruff lint/format and strict mypy pass. Fourteen frontend component tests, API generation, TypeScript/Vite build, ESLint and Prettier pass; initial new-fixture TS2739 was corrected.

The real API/database/browser candidate-review journey passed (3.9s; 11.2s total), requiring explicit confirmation, persisting the chosen website across reload and removing stale choices. At 375/1440 there was no overflow or axe violation; mobile screenshot inspected. The existing company edit/source/all-jobs journey also passed (12.0s; 22.2s total). Search responses were synthetic; the browser fixture forces mock mode and never calls Brave. No live provider, arbitrary-page network, generic collection or complete discovery coverage is claimed. Build still warns about a >500 KB minified chunk (156.69 KB gzip).

2026-10-07 generic collection: full backend suite passed 129 tests (56.75s), followed by sixteen generic/inventory tests (6.22s) after the duplicate-card guard. Validated structured employer attribution, expired/unverified withholding, source creation with non-authoritative coverage, worker-to-inventory revisions, restart/replay of page frontiers, bounded link expansion, partial initial baseline versus later new jobs, and preservation of roles after repeated empty pages. Migration consistency, Ruff lint/format and strict mypy pass. API regeneration/frontend build/lint pass (156.79 KB gzipped JS; existing chunk warning). Tests inject fetched pages; actual generic site coverage, selectors, browser/AI fallback and network isolation remain unverified. No new browser acceptance is claimed for this phase.

2026-10-07 browser setup blocker: Python Playwright uv-add through the package-registry Python index exited 2 with `invalid peer certificate: UnknownIssuer` fetching its lxml index. Manifest/lock remained unchanged. No workaround/retry or browser isolation validation occurred; new user instructions are required before retrying with changed trust settings.

2026-10-07 unstructured extraction contract: seven mocked-inference tests passed (1.47s); Ruff and strict mypy pass. Tests cover task-specific configuration, page-only payloads, exact evidence, observed-link enforcement, duplicate/multi-job ambiguity, explicit uncertainty and input limits. No live model call, semantic quality evaluation, queue integration or browser fallback acceptance occurred.

2026-10-07 latest supplied-CV check: aggregate-only local extraction passed (one page, 3,847 characters); file remains Git-ignored, with no AI request or persisted extracted text. Three targeted synthetic PDF/DOCX format regressions passed in 3.06s. Reading order across arbitrary layouts and semantic accuracy remain unverified; image-only OCR is unsupported.

2026-10-07 matching/persistence/API phase: 159 backend tests passed (61.78s), including 26 targeted matching/inventory/API regressions previously passed in 13.76s. Current-version filtering admits match and possible_match, retains rejected/stale/failed jobs in All jobs, and exposes current explanations plus independent operation errors. Mock/live identity separation, stale model/profile/job revisions, bounded fan-out/replay, lost leases and profile-purge races are covered. Migration/model consistency, Ruff lint/format, strict mypy and generated API/frontend build pass. Synthetic inference only: no live model quality, matching portal journey, notification eligibility or production deployment claim.

2026-10-07 job owner actions and assessment UI: 161 backend tests passed (27.64s) before the final Idempotency-Key addition; sixteen assessment regressions passed afterward (12.84s). Covers closed-job reassessment, joining pending/current work, terminal retry, keyed replay and cross-job conflict, feedback revision conflict and independence from AI categories, and purge cleanup. Migration consistency, Ruff and strict mypy pass. Final frontend suite: 19 tests (7.59s), build/lint pass, covering safe evidence display, mock labels, failed-assessment recovery, dirty-feedback preservation, network replay and cached-data purge. Real API/database/browser feedback save/reload and filtered navigation passed in 6.3s (10.9s total), with zero axe violations/no horizontal overflow at 375/1440; mobile screenshot inspected. The final key/header and purge-cache additions have targeted/component coverage rather than another browser run. Complete mocked assessment-worker-to-shortlist and live model quality acceptance remain pending.

2026-10-07 integrated mock matching and queue handoff: final backend suite passed 166 tests (86.40s); all eight real API/database/worker/browser journeys passed (1.8m). The matching journey (13.7s) uses authored synthetic source postings and exact-input AI responses, verifies both shortlist categories, inspectable evidence, unrelated-function exclusion, All jobs access and automatic reassessment after a saved role-family change. No overflow or axe violations at 375/1440; final mobile screenshot reviewed. Production-minute scheduling is not simulated by this journey: the browser fixture invokes real dispatch every two seconds.

Broader validation exposed two failures: a browser heading/navigation race (fixed with a detail-URL wait), and a real queue race where SKIP LOCKED acknowledged a dispatcher-locked intent without claiming it. A concurrent PostgreSQL regression failed on the original claim and passed after switching to a bounded blocking row lock. Final browser and backend suites pass after that fix. Fixture tests cover unknown-input blocking, evidence rejection, production/live separation and absence of HTTP/billing. Ruff/format/mypy and frontend build/lint/format pass. Real employer fetching, selected-model judgment, policy-upgrade reconciliation, notifications and production network/recovery gates remain incomplete.

2026-10-07 policy reconciliation: 170 backend tests passed (36.88s); all five reconciliation tests passed afterward (0.99s) with the final periodic-control-tick check. PostgreSQL coverage includes 100-or-smaller batches, active/unknown versus closed scope, policy upgrade and rollback with newer inventory, concurrent ticks, mode separation, missing profile/model guards and no automatic retry of existing failed/blocked intents. Obsolete-policy fan-out is rejected. Ruff/format/strict mypy pass. This is scheduling/idempotency evidence with synthetic fixtures, not live matching quality or notification delivery acceptance.


### Persisted extraction locally validated

2026-10-07: Full backend suite passed 184 tests (75.02s), including snapshot replay/retry, missing-model explicit mapping, open/employer filtering, source/new-epoch/mode/lease invalidation, raw retention, input bounds and persisted pagination across fetch/AI queues. Existing CV retention and inventory omission protections pass. The initial three regressions were corrected: tests now execute the AI continuation and direct supported ATS links take precedence over plain careers-source registration. Ruff lint/format and strict mypy (52 application files) pass. Alembic check reports no new upgrade operations against migration 0012. One existing Starlette/httpx deprecation warning remains.

These are mocked-inference workflow checks, not real-source/model-quality or browser/network-isolation acceptance. No frontend response contract changed. Browser dependency setup remains stopped at the recorded UnknownIssuer error, with no dependency retry, trust workaround or live provider call. Saving this phase locally; next implement the timezone-aware notification scheduler and durable digest/delivery ledger. The complete PLAN.md goal remains active.


### Notification calendar foundation

Extraction phase saved as 69dd4b5. Added owner-timezone daily slot calculation, independent of the host timezone and collection interval. It chooses the first repeated occurrence and advances nonexistent minute-granular wall times to the first valid minute, including half-hour gaps and skipped dates. Future-slot calculation never schedules a downtime catch-up. Nine calendar tests passed (1.14s), covering London winter/summer/gap/fold, Lord Howe, Apia, owner-local dates and naive-time rejection. Ruff and strict mypy (53 files) pass. This is the calendar foundation only: persisted settings/slots, event and delivery ledgers, worker/API/UI wiring, ntfy transport and recovery remain to implement. No message was sent or dependency fetched. The complete goal remains active.


### Notification ledger validated locally

Full backend suite passed 210 tests (87.91s). Final policy review then added suppression for jobs already reserved/sent/ambiguous in the same integration mode and explicit current assessment-error/unresolved-watch/matching-availability fields. The resulting targeted ledger suite passed all 22 tests (5.57s); the preceding category/ambiguity cases passed 21 tests (9.12s). New qualifying roles from prior not-match results receive a reassessment label; possible/strong changes for already-notified roles do not alert again. Current failures are selected by current assessment identity, not historical failed operations.

Ruff lint/format and strict mypy pass (57 source files). Alembic consistency reports no new upgrade operations against migration 0013. OpenAPI types were regenerated and the final frontend TypeScript/Vite build passed (158.41 KB gzipped JavaScript). Existing Starlette/httpx deprecation and frontend chunk-size warnings remain. No dependency fetch, trust workaround, live AI request or ntfy publish occurred.

Next implement delivery attempts, bounded retry, ambiguous-send recovery and definitely-unsent membership release, followed by portal configuration/history and transport validation. Digests currently persist as pending/skipped; notification transport is not yet functional. The original PLAN.md goal remains active, and the Python browser dependency certificate blocker is unchanged.


### Notification delivery locally validated

Full backend suite passed 235 tests (88.62s). After final recovery/cooldown refinements, 44 delivery/transport/ledger tests passed (22.77s), followed by 22 focused delivery/transport tests after large/padded Retry-After handling (8.97s). Ruff lint/format and strict mypy pass (59 files). Migration 0014 matches ORM metadata: Alembic check reports no new upgrade operations. Generated OpenAPI types and frontend TypeScript/Vite build pass (158.41 KB gzipped JavaScript). The SQLAlchemy DISTINCT ON warning was removed; the existing Starlette/httpx and frontend chunk-size warnings remain.

Validated persisted pre-send state, acceptance receipts, replay safety, bounded definite-failure retry, unknown-outcome reservation, crash recovery, in-flight purge, destination changes and cooldown carry-over without real publishing. AGENTS.md now explicitly requires regular written progress checkpoints, including during long phases, and the top-level progress summary is refreshed. Saving this phase locally. Manual resend/test-message actions, notification portal UX and actual local ntfy/deployment acceptance remain next; no release completion is claimed. The existing browser dependency certificate blocker remains unchanged and was not retried.

### Notification actions and Settings acceptance — 2026-10-07

Full backend: 245 passed (118.74s); frontend: 23 tests passed, ESLint/Prettier pass. Ruff/format and strict mypy pass (60 application files). Migration 0015 Alembic check reports no new upgrade operations. Production build passes (161.85 KB gzipped JS; existing chunk-size warning). All nine real API/database/worker/browser journeys passed (1.3m); after scoped notification form spacing corrections, the affected notification journey passed again (16.2s; 25.7s total). Notification checks cover schedule persistence, owner timezone, explicit mock delivery and truthful failed/mock status, zero axe violations/no overflow at 375/768/1440, and landscape/reduced-motion/enlarged-text overflow. Mobile/desktop screenshots reviewed.

Backend regressions cover explicit request replay, latest-attempt conflicts, duplicate acknowledgement, fresh manual retry windows, standalone test retries, historical unknown protection, superseded membership and purge. Component tests cover retained schedule edits/conflicts, request-key reuse, unknown resend acknowledgement and removed content. These are local mocked-provider checks; real ntfy/phone delivery and deployment isolation remain unverified.

### Company coverage/count acceptance — 2026-10-07

Full backend suite: 247 passed (135.60s); seven focused overview/inventory tests passed earlier (4.14s). Counts deduplicate jobs across sources and preserve availability categories; scheduling excludes disabled sources, respects cooldowns and suppresses paused-company dates. No-source and incomplete coverage remain distinct. Ruff/format and mypy pass (61 files); frontend component suite: 23 passed, with API generation/build/lint/format passing. Affected real company and discovery browser journeys: two passed (50.0s), including list/detail counts and retained All jobs navigation, with zero axe violations/no overflow at 375/1440 and screenshots inspected. Final screenshot review prompted copy-only singular/plural corrections. No live collection or market-completeness claim is made.

Final company-coverage production build and ESLint passed after pluralization corrections (162.41 KB gzipped JS; chunk-size warning remains).

### Conditional HTTP snapshots — 2026-10-07

Full backend suite: 268 passed (73.87s), with the existing Starlette/httpx warning. Focused inventory/generic/extraction/fetcher suite passed 61 tests (22.42s) before the final updated-representation regression. Migration 0016 Alembic check reports no new upgrade operations; Ruff/format/mypy pass (62 application files). Evidence covers repeated 304s without false omissions or duplicate revisions, changed 200 replacement, unusable cache rejection, source/URL/redirect separation, source edits and lost leases, date-sensitive HTML reparsing, Last-Modified and ETag validation, no-store/Vary exclusions, compressed metadata on bodyless 304s, 200-page limits and expiry preserving normalized jobs. The final key-only retention query passed the focused cap/expiry regression (0.72s). No live HTTP, browser fallback, real employer coverage or deployment isolation is claimed.

### Company-scoped job browsing — 2026-10-07

Affected backend suite: 23 inventory/assessment tests passed (7.38s); Ruff/format/mypy pass (62 application files). Coverage includes active-or-unknown default versus explicit single-state filters and saved-but-unmapped model rejection for shortlist/manual reassessment while preserving All jobs access. Frontend full suite passed 25 tests before final refinements; five focused list/purge tests passed afterward (3.86s), including fixed company scope and hiding cached shortlist data when matching becomes unavailable. Final build/lint pass (162.99 KB gzipped JS, existing chunk warning).

Initial full browser run passed seven journeys and failed two on the new inline notice links relying only on color (axe link-in-text-block, 2.26:1 text-to-text contrast). Scoped underlines corrected that issue. The affected company/discovery rerun passed both journeys (38.1s), including inline search/availability, retained company scope, return-link/native-back filters, scroll restoration and focused originating link. Axe/overflow checks pass at 375/768/1440; mobile/desktop screenshots inspected. No final all-nine rerun or live source/model acceptance is claimed.

### Declarative website rules — local backend validation

Full backend regression: 287 passed in 73.70s, with the existing Starlette/httpx deprecation warning. The earlier focused selector/API/generic-inventory batch passed 24 tests in 7.86s. Coverage includes required/ambiguous/private-link fields, visible-text extraction, employer attribution, explicit empty versus missing cards, conflicting duplicate jobs, expiry/closed markers, same-site pagination, unsupported selectors, revision-protected save/clear, ATS rejection and recent cached previews without network calls. A real database/worker regression confirms stored rules are used and three successful empty generic checks preserve an observed job with zero omission count and no AI handoff.

Ruff, formatting (117 files), strict mypy (63 application files), generated OpenAPI types and frontend production build pass (162.99 KB gzipped JavaScript, existing chunk warning). No database schema migration or frontend interaction change was introduced. No browser-editor, live website, rendering or deployment acceptance is claimed.

### Website extraction portal — local validation

All 28 frontend component tests pass (13.70s), including edit retention across background refresh, revision-conflict comparison/rebase and preview invalidation on input changes. Final production build and ESLint pass (164.78 KB gzipped JavaScript; existing bundle warning); formatting passed before the final scoped CSS change, which was subsequently formatted. Browser seeder Ruff/format checks pass. The real API/database browser journey passed first in 25.4s, then in 20.9s after a screenshot-driven layout correction (12.8s test time). It verifies saved-page preview, custom-rule persistence after reload and explicit automatic-mode restoration. Axe and overflow checks pass at 375/768/1440; mobile/desktop screenshots inspected, including final desktop layout. No live source/model call occurred. Full backend evidence remains the prior 287-test pass; no backend application behavior changed in this slice.

### Docker configuration and isolated runtimes — 2026-10-08

The consolidated ten-service Compose template passes checks for network memberships, private port binding, digest references, completion-ordered bootstrap and exact secret scopes. Six unsafe configuration variants were rejected (backend publishing, all-interface edge bind, fetcher/core membership, fetcher DB-secret mounting, external fetch network and floating PostgreSQL image). Synthetic initialization in a temporary directory verifies fresh credentials/files, repeated-run preservation, 0700/0644 directory/file modes and rejection of an exposed secret directory. No actual deployment secret file was read or changed. Ruff and formatting pass for all 14 scripts.

ntfy v2.27.0 was pulled once successfully with digest `sha256:f2419f405127afa868f10985c1a41449e673477cee1eb19994339a5ae8b592e7`. The non-root ntfy image and Caddy runtime-base stage build successfully from cached bases with no package installation. Initial Caddy execution failed because its file-capability request conflicted with dropped capabilities; removing that unnecessary capability for high container ports resolves the failure. Caddy adapt/config validation exits 0 under non-root, read-only, cap-drop-ALL and network-none settings.

`python3 scripts/check-ntfy.py` passes, including the exact Compose health command, anonymous read/write denial, publish-only bearer token, denied publisher reads/unrelated topics, reader-only access and a matching cached message receipt. It uses only synthetic credentials in a disposable network-none container, publishes no ports, contacts no real clients and removes the container. The final rerun after tightening the health expression passed.

These are isolated/runtime-configuration checks, not end-to-end deployment acceptance. Full frontend/backend image builds, browser-enabled fetching, stateful network isolation, LAN/tailnet ingress/TLS client trust, worker-to-ntfy integration, secrets on the actual host, backup/restore and live provider/source quality remain open. The Python dependency certificate blocker and current private-registry lockfile portability issue remain recorded; no retry, proxy/trust change or production startup occurred.

### Route loading and recovery — 2026-10-08

Production build, ESLint and Prettier pass; all 30 component tests pass (3.86s). Initial JavaScript is 137.34 KB gzip, down from 164.78 KB; inventory/profile/settings have separate chunks and the oversized-chunk warning is gone. This is build output, not a measured deployment latency improvement. Slow-loading and failed-route component tests verify loading announcements, retained navigation and a single main landmark.

All 11 real API/database/worker/browser journeys passed in 2.3 minutes. Coverage includes profile review/conflicts/purge, model/billing settings, company detail/filter/scroll/focus return, discovery, matching, notifications and website rules, with existing responsive/axe checks. The added journey deliberately aborts the profile module download, verifies navigation to Settings still works, and reloads successfully after the request block is removed (4.0s). This uses the local Vite server, not the final Caddy deployment. No backend behavior, dependency version or provider integration changed.

## Basic recovery scripts — 2026-10-08

The recovery suite now includes encrypted-stream/integrity checks, public-key-only backup, producer and consumer failures, bounded timeout, symlink/traversal rejection, mocked writer-stop/restart failures, and real disposable PostgreSQL/volume checks. The first expanded run passed 14 of 15 tests; the new isolated restore drill exposed a chmod-after-chown failure in its restricted helper. Reordering those operations fixed the affected drill, which passed in 28.219s. It restored all five archives into fresh volumes, checked synthetic file bytes/private modes as UID 10001, restored a custom PostgreSQL dump and queried its synthetic row, and checked removal of the restore container. Tests clean up only their own databases/volumes/containers. No production backup or restore was attempted.

This evidence does not establish application-level recovery, production quiescence orchestration, nightly scheduling/retention, measured RPO/RTO, or intended-host deployment acceptance. Backup restart failure orchestration is mocked; a real deployment drill remains required.

Final recovery regression: all 15 checks passed in 22.043s (exit 0). Ruff and formatting passed for all 18 scripts; git diff --check passed.


## Backup retention and timer templates — 2026-10-08

Six synthetic retention tests pass (0.082s), covering seven daily/four weekly selection, same-day duplicates, ISO year transition, protected foreign/incomplete/future/unexpected directories, symlink/hardlink exclusion and no pruning after failed capture. Only temporary synthetic snapshots were removed. An initial deletion-count assertion used a fixture time ahead of the wall clock; freezing the test clock resolved the mismatch without changing retention behavior.

Systemd unit verification passed for both supplied templates (exit 0); unrelated existing host-unit PIDFile warnings were emitted. Calendar parsing showed the next two 02:00 host-local occurrences. No units were installed/enabled, no real backup pruned, and no scheduled execution or downtime/restart acceptance is claimed.

Final combined recovery/retention run: 21 tests passed in 11.983s (exit 0). Ruff/format passed for all 20 scripts; git diff --check passed.


## Live OpenRouter probes on the deployment host — 2026-10-09

First live OpenRouter traffic, run through `scripts/validate-live-api.py --execute-live` (run `20261009_142304`) with the temporary key bridge and the cumulative run ledger. Luna chat probe (`openai/gpt-6-luna`, profile_analysis, synthetic probe payload): HTTP 200, terminal state `succeeded`, returned model `openai/gpt-6-luna`, cost $0.00000635, latency 6336 ms, generation ID recorded. Jev Decisions probe (`typesafe/jev-1.13`, job_matching, typed "ok" question, `provider.data_collection="deny"`, `zdr=false`): HTTP 200, terminal state `succeeded`, returned model `typesafe/jev-1.13-20260917` (accepted by the exact-prefix dated-version rule), cost $0.00001369, latency 490 ms, generation ID recorded. Ledger after the run: 2 attempts, $0.000020042 known, nothing held. Key metadata (1 GET): usage $0, limit $5, resetting monthly — recorded as advisory notes per the owner's same-day decision that the US$1 validation cap is advisory; the ledger remains the pre-dispatch admission gate.

Also validated live: the capability preflight defect fix (tiered `overrides`/`discount` pricing had blocked all Luna endpoints; fixed and regression-tested offline), the `--execute-live` key-bridge lifecycle (created 0600 before first settings use, removed on shutdown, no leftovers), and Gate A offline refusals in the same run.

Limits: one probe per protocol, synthetic payloads only. This does not establish deny enforcement beyond request acceptance (not externally observable), matched-task quality, prompt usefulness, fetcher isolation, digest delivery, or deployment acceptance. No retries were sent; no live request exceeded the advisory cap.

## Progress/approach review checks — 2026-10-09

Reviewed baseline `594b1ab` plus the pre-existing uncommitted DNS rule/test edits. Fresh `python3 scripts/test_fetch_rules.py` exited 1: six tests run, four failures. Install/reinstall fail with `BLOCKED: expected 12 DOCKER-USER and 6 INPUT managed rules, found 8 6`, followed by post-install rollback. The drift assertion fails because installation left zero rules. This is mocked command execution in temporary files, not a host-firewall or Docker validation. No fix was applied during this review.

Source inspection confirms the harness has no pre-rule DNS baseline, the Jev conversion hardcodes unknown domain/important uncertainty, and the mocked insert-failure case fails on its first insertion rather than testing cleanup of a partial installation. Findings and acceptance limits are recorded in REVIEW.md. Historical backend/browser/live passes were read, not reproduced; no secret/ledger read, dependency operation, live request or privileged runtime check occurred.

## Review findings resolution and Jev Phase D verification — 2026-10-09

Addressed the review findings in [REVIEW.md](REVIEW.md) and [ADVISE.md](ADVISE.md) across installer, harness, and Jev matching adapter:

1. **Firewall installer and mocked transaction suite:**
   - Restored the pre-exception 8 DOCKER-USER and 2 INPUT ruleset in `deploy/fetch-control-rules.sh`, removing the speculative DNS exceptions.
   - Fixed installer idempotency: verified existing `8 2` ruleset is kept (or replaced on address drift) rather than stacked; converted `verify()` and `assert_preconditions()` to return-based status so failures are not swallowed inside subshells or conditionals.
   - Added `test_apply_failure_rolls_back_partially_installed_rules` simulating failure on the 5th insertion after 4 successful insertions, verifying 0 rules remain.
   - Fresh offline check: all 7 tests in `scripts/test_fetch_rules.py` pass (exit 0, 1.89s).

2. **Fetcher DNS resolution and destination enforcement (Option C: proxy delegation):**
   - Implemented proxy delegation in `backend/app/fetcher/http.py`: `resolve_public(url, proxy_url=self.config.proxy_url)` immediately validates IP literals locally without DNS (rejecting `127.0.0.1`, `192.168.x.x`, `10.x.x.x`, `::1` with `destination_denied`).
   - When local DNS fails with `OSError` (the demonstrated behavior of Docker's internal-only bridge topology), and a proxy is configured, resolution and connection-time destination filtering are delegated to Squid (`egress-proxy:3128`), which resolves hostnames over `public_outbound` and enforces `acl nonpublic dst` at connection time.
   - Mapped Squid 403 `ERR_ACCESS_DENIED` to `FetchFailure("destination_denied")`, Squid 503 `ERR_DNS_FAIL` to `FetchFailure("source_dns")`, and HTTPS CONNECT proxy error 403 to `FetchFailure("destination_denied")`.
   - All 26 fetcher unit tests pass (exit 0, 3.51s).

3. **Jev Decisions matching adapter (Phase D offline implementation):**
   - Implemented 5-anchor relevance scoring mapped by `round_half_up(25 * native_score)` to 0..100; tested boundary scores (native 1.16->29, 1.18->30, 1.22->31, 2.36->59, 2.38->60) and half-ties.
   - Bounded exact quotation candidates (<= 500 chars) presented in full in question criteria; candidate budget capped at `MAX_CANDIDATES_PER_SPAN = 50` with visible `OperationError("ai_input_too_large")` at task boundary; tested with 3,522-character description verifying duty at character 3,500 is in candidate pool and validates.
   - Removed mechanical profile fallback for score evidence: when a relevance score is assigned, `score_profile_evidence` strictly requires a selected profile candidate; missing or `insufficient` raises `ValueError("relevance score outcome lacks selected profile support")`. Tested with specific candidate skill citation.
   - Implemented dynamic `domain_status` and `domain_evidence` for `focus` domain mode; verified domain conflict derives `not_match`, and unsupported known domain outcomes (`met` or `not_met` with insufficient evidence) are rejected with `ValueError`.
   - Implemented dynamic `important_unknowns` Choice question; verified that `score >= 60` with `important_unknowns=false` derives `match`.
   - Implemented Choice `plausible_connection` (supported / unsupported / unknown) without probability coercion; verified unknown does not coerce to true, and supported connection strictly requires selected profile candidate evidence without mechanical summary/experience fallbacks.
   - Implemented per-criterion comparability check (`preference:{id}:comparability`), ensuring incomparable terms (e.g. salary) stay unknown with `comparable=False`.
   - Re-versioned policy to `POLICY_VERSION = "broad-v2"` and prompt/schema to `"matching-decisions-v2"`, ensuring old assessments are treated as historical.
   - Full backend regression suite: all 340 tests pass (exit 0, 68.26s) against the disposable PostgreSQL 17 test database.

4. **Budget and durable ledger reconciliation:**
   - Durable ledger `.data/live_run_ledger.json` records 2 attempts, US$0.000020042 known spend, US$0 held spend.
   - Owner confirmed on 2026-10-09 that the US$1 cap is an advisory validation budget, with the key's $5 monthly limit as an outer provider backstop.
   - Remaining allowance under advisory cap: 58 attempts, US$0.999979958.

5. **Runtime blocker (Snap Docker NoNewPrivs EPERM - confirmed by kernel audit):**
   - Owner provided kernel audit log records from `sudo dmesg -T | grep -E "apparmor|audit|DENIED" | tail -30`:
     `apparmor="DENIED" operation="exec" class="file" info="no new privs" error=-1 profile="snap.docker.dockerd" name="/bin/echo" pid=274035 comm="runc:[2:INIT]" requested_mask="x" denied_mask="x" fsuid=0 ouid=0 target="docker-default"`
   - Confirms that the Snap confinement profile `snap.docker.dockerd` on Ubuntu Noble denies `execve` into container profiles when `PR_SET_NO_NEW_PRIVS` is set.
   - Runtime hardening flags (`security_opt: [no-new-privileges:true]`) in `compose.yaml` are strictly preserved and asserted by `scripts/check-deployment.py`. Container cleanup in `scripts/check-proxy.py` guaranteed even on startup failure.

6. **Limits:**
   - No new live inference requests were made in this session (spend remains US$0.000020042).
   - Gates C (actual generative schemas), D (live semantic evaluation), E, F, real container isolation matrix, and deployment gates remain open.

## UI/UX review evidence — 2026-10-12

Documentation-only review at baseline `e6b1fa9`; findings and future acceptance suggestions are in [UIUX_REVIEW.md](UIUX_REVIEW.md). No frontend implementation changed.

- `cd frontend && npm run test:e2e -- --output=/tmp/jobfinder-uiux-foundation`: **exit 1, 3 failed**. At 375/768/1440px, `frontend/tests/browser/foundation.spec.ts:67` timed out after 5000ms expecting the Jobs heading to be focused; received inactive. Login axe assertions completed first. Later layout/Jobs axe/Settings/logout checks were not reached. Traces/error contexts retained under the stated temporary output directory.
- `node /tmp/jobfinder-uiux-inspect.mjs`: **exit 0**. Installed headless Chrome and an isolated loopback Vite server; synthetic API fixtures only, non-local requests blocked. Jobs, Companies, company detail, job detail, Profile and Settings inspected at 375/768/1440px with height 900px: **18 axe scans with zero violations**, ordinary-fixture document widths matched viewports; no unexpected requests/page errors. Current screenshots and DOM results retained in `/tmp/jobfinder-uiux-review/`. Server/browser closed on completion.
- Targeted browser observations: profile changes lost on route departure/return; a blank preference in a collapsed disclosure left its validation error hidden with no alert and focus on Save; a background 503 removed cached company and job content; a 203-character unbroken job title caused 3008px document width at 375px; lazy navigation focused main rather than the destination heading. These are reproduced defects/limitations, not passing acceptance results.
- CSS token calculations: `#dce2e9` against white 1.304:1; muted text on white 5.895:1; muted text on page background 5.548:1; accent on white 6.453:1; body text on white 14.629:1. Control-boundary contrast must be distinguished from decorative separators.
- Impeccable context/detector launcher attempts with downloads disabled exited 127 without output. Automated Impeccable scan unavailable, not a clean scan. Initial sandbox shell execution failed with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` (exit 1); approved escalated execution worked. No dependency operation or workaround was attempted.

No screen-reader/physical-device/cross-browser/actual-zoom/performance benchmark, backend integration suite, live provider or notification check was run. Historical broader pass records are not fresh evidence for this review. Proposed acceptance checks in UIUX_REVIEW.md remain unexecuted.

Review-document checks passed: 14 ordered findings, all local Markdown links resolve, all cited frontend line numbers exist, new report has no trailing whitespace, final newlines present. Initial fixture-length assertion failed and corrected the draft from 196 to the measured 203 characters; no application behavior changed. Temporary review server ports 5173/5174 confirmed closed.
