# Progress, approach and attempts review

## Current progress review — 2026-10-10, baseline `d93a67b`

The agent has made meaningful progress: the Docker R1 workaround remains intact, the selected provider now accepts real profile/extraction schemas, and Jev has returned one valid live matching result. The main concern is overclaiming acceptance. The new isolation runner does not establish the complete section 9.2 boundary despite the progress/commit wording, and the deployment preflight now permits enabling fetching without verifying that boundary. Keep full isolation acceptance open and fetching disabled on the real deployment until that evidence exists.

This review changes documentation only. No implementation fix, container/network/firewall change, dependency operation, provider call or commit was performed. Earlier sections remain historical; use the status and instructions here for continuation.

### Status at this review

| Area | Current assessment | Evidence and limits |
| --- | --- | --- |
| R1 Docker startup | Resolved for the project compatibility path; no migration needed. | Prior actual service/Compose/recovery checks proved in-container NNP. Latest changes preserve that path; fresh 3-test runtime-configuration suite passes. This review did not repeat container starts. |
| Luna profile/extraction | Basic live schema compatibility demonstrated according to the execution record. | The launcher now calls actual `analyze_profile()` and `extract()` with small synthetic inputs. Useful progress beyond generic `ok` probes; broader semantic accuracy and application integration remain unproven. |
| Jev matching | One live contract-valid assessment demonstrated according to the execution record. | Actual `assess()` and domain validators are used. The launcher does not assert a gold category, persist a current `JobAssessment` or verify that the portal explanation is useful. Broad model-quality/unknown/function-boundary cases remain pending. |
| DNS/proxy collection | Implementation candidate exists; usable real fetching remains unproven. | Local DNS failure can delegate to Squid, but the new runner never successfully fetches a public hostname through an actual proxy. A real positive path is needed to close this blocker. |
| Fetch isolation | Partial checks passed; full section 9.2 gate remains open. | Mocked redirect/body/limit checks, network-none Squid ACLs, containerized auth/schema checks and one internal-network direct-egress failure cover parts of the matrix. They do not prove the deployed directional/network boundary. |
| Fetch enablement | Parameter implemented, acceptance guard insufficient. | Repository default remains false. An env-file switches preflight into a mode accepting true without rule verification or acceptance evidence; do not treat that as approved safe enablement. |
| Accounting | Latest aggregate record reconciles. | Fresh read of aggregate ledger fields confirms 19 attempts, US$0.000836348 known spend, zero held. Remaining under the latest US$1/60-request instruction: 41 requests and US$0.999163652. No inference was sent by this review. |
| Product release | Still incomplete. | Gate E semantics, Phase F live worker/API/portal integration, representative real company coverage, browser containment, private ingress, scheduled device digest and deployed recovery/timer acceptance remain outstanding. |

There is no new failing runtime/environment condition demonstrated by these commits. The immediate blocker is incomplete safety/positive-path evidence and unreliable acceptance classification. The agent can continue improving the proof with the existing runtime; another CV, key or Docker migration is not needed.

### Must fix before calling the affected gate passed

1. **The claimed full isolation matrix is not exercised** ([scripts/test-fetch-isolation.py](scripts/test-fetch-isolation.py), `test_disposable_container_isolation`, mocked redirect/body tests and `main`).
   - **What this is:** The two RPC containers run on the default Docker network with a published loopback port and proxy URL `http://127.0.0.1:3128`, where no proxy is started. A third probe uses one internal network. Squid runs separately with network none; redirect/size tests use host-side MockTransport.
   - **Problem:** There is no successful public HTTP/HTTPS fetch through Squid, no worker on `fetch_control`, no proxy on `fetch`/`public_outbound`, no installed/verified directionality rules and no controlled live worker/core/host/LAN/tailnet denial or rebinding test. Browser containment, robots and timeout acceptance are also not established by this runner. The private URL checks validate schema/engine guards; they do not show a compromised fetcher cannot reach private services.
   - **Agent instruction:** Retain these checks as clearly labelled unit/partial integration evidence. Reopen the section 9.2 claim and build one scoped disposable topology matching the production connections and shared rule logic. Require a real permitted fetch and real denied connections to alive controlled listeners; add connection-time hostname/private-rebinding/redirect proof. Keep browser-specific acceptance separately open until rendering exists. Record exact image IDs/source correspondence, topology, rule state and every required row's result. No rewrite or extra resolver service is implied.
   - **If skipped:** Collection may still fail before the proxy, while a compromised fetcher may reach worker/private addresses despite all the current checks passing. Neither the DNS blocker nor the complete safety gate can be called resolved.

2. **The direct-egress test treats any Docker failure as successful isolation** ([scripts/test-fetch-isolation.py](scripts/test-fetch-isolation.py), lines 459–477).
   - **What this is:** The runner declares PASS whenever `docker run` returns nonzero. This probe omits `--pull never` and does not use the NNP payload wrapper.
   - **Problem:** A fresh isolated AST/mock self-check supplied Docker exit 125 with “container failed to start”; the runner still reported PASS. Missing-image/pull errors, daemon access failures and program failures can therefore masquerade as network denial. A failed image fetch would also be concealed instead of triggering the project's dependency-failure boundary.
   - **Agent instruction:** Prove container/command startup first, use cached images with `--pull never`, apply the same payload hardening, and make the socket probe report structured success versus expected network denial versus unexpected execution error. Verify live listener reachability/liveness where a denial must prove policy. Fail on unexpected Docker/probe status and retain sanitized diagnostics. Add the exit-125 regression before another privileged acceptance run.
   - **If skipped:** Broken test execution can certify a nonexistent safety boundary. The recorded Errno 101 may be genuine for the previous run, but the test cannot reliably establish it on future runs.

3. **The enabled deployment flag is not backed by verified isolation** ([scripts/check-deployment.py](scripts/check-deployment.py), `check` and `main`; [compose.yaml](compose.yaml)).
   - **What this is:** Supplying any env-file enables `allow_verified_isolation`, which accepts the true flag without checking actual firewall state or acceptance evidence.
   - **Problem:** A fresh offline self-check set the flag true in an otherwise valid config: normal template mode rejected it, but deployment mode accepted it without proof. An operator can enable arbitrary fetching while directionality rules are missing or stale. This is especially concerning while finding 1 is open.
   - **Agent instruction:** Keep real deployment fetching disabled. Tie enablement to an explicitly reviewed passing acceptance result for the effective topology plus current rule/address verification; keep startup, backup and restore on that same effective configuration. Use the existing rule verifier and a small local evidence/check mechanism rather than a new control framework. Document rejection when rules are absent, container addresses drift or proof concerns a different image/configuration. An env-file's existence alone is not evidence.
   - **If skipped:** The gate becomes an unchecked checkbox even though the safe repository default remains false.

4. **A redirect test can pass before exercising its redirect** ([scripts/test-fetch-isolation.py](scripts/test-fetch-isolation.py), `_probe_redirect`).
   - **What this is:** It catches every `FetchFailure` and `ValueError` as successful private-redirect rejection, and uses the shared `/tmp/test_origins.sqlite3` state.
   - **Problem:** Failure resolving the starting `example.com` URL, cooldown/state contamination or an unrelated validation failure can make the test green before the mocked redirect is reached. This is the same causal mistake as the earlier DNS baseline issue.
   - **Agent instruction:** Make the mock test deterministic with its own temporary state and controlled starting-host resolution; assert the mock redirect handler was reached and the resulting code is the intended destination denial. The real proxy redirect acceptance still needs a separate controlled network test. Do not regard broad exception catching as security proof.
   - **If skipped:** A failed prerequisite can keep the redirect check green while the behavior it claims to test remains broken.

### Should fix while completing acceptance

5. **Gate C/D wording is stronger than the launcher assertions.** `run_schema_checks()` directly calls adapters with `operation_id=None`. Profile success checks a `Facts` instance and non-None summary; that summary field is a string with an empty default. Extraction asserts at least one job; matching asserts an `Assessment` instance and prints its fields. These prove compatibility and local validation, but not declared expected facts/category, a current persisted assessment or a useful portal explanation. Record “basic live schemas and one validated judgment passed” now. Complete the missing operation/Settings/usage path and current persistence/display evidence in Phase F, and inspect this live case against its declared expectation before full Gate D sign-off. Empty optional reason arrays alone are not a failure if the actual displayed fields explain the result well.

6. **Request usage needs a revised allocation, not repeated connectivity probes.** The ledger has grown from 2 to 19 attempts, while the top checkpoint lists only the latest successful probes/schema cases. `main()` always runs both paid `run_probes()` before `--schema-checks`, so repeating one schema case also repeats successful connectivity calls and creates fresh task revisions. Record a sanitized attempt/outcome breakdown, including failed/repair calls, and let the next batch reuse established connectivity. With 41 requests left, reserve the integrated-journey allowance before selecting semantic cases and targeted repairs; the original 20 cases + 20 revision attempts + 10 integrated requests would exceed the remainder. No larger budget is required just to investigate isolation, and this review authorizes no paid batch.

7. **Canonical check evidence is lagging behind the new progress claims.** Neither `668f340` nor `d93a67b` updates VALIDATION.md with their new executions; DECISIONS.md still lists 2 attempts and open gates, while PROGRESS.md lists 19 and C/D passed. Update the actual-results record after each batch with scoped passes/failures, exact invocation, image/model versions, sanitized billing and unresolved rows. Label historic snapshots clearly. Do not silently erase the prior failed attempts or replace a detailed matrix with a blanket “all tests passed.” This review adds its own fresh check evidence, not an invented execution record for the other agent.

### Concrete next assignment for the implementing agent

1. Correct the acceptance status: R1 compatibility passed; live schema/judgment basics passed; complete real isolation and broader model/application acceptance open. Leave real fetching disabled.
2. Fix the false-positive test classifications and add small offline regressions, then prepare the exact disposable topology/rules/listeners and rollback. Reuse the current runtime workaround and shared firewall functions. Do not migrate Docker or change unrelated host services.
3. Run the permitted real proxied positive path and required network denials with current-code images. If a scoped firewall operation requires owner execution beyond existing authority, provide the concrete reviewed command and why it is needed; do all preparation first. The owner need not choose the architecture or supply new model credentials for this step.
4. Only after that boundary passes, finalize enablement with current proof/rule verification and consistent deployment/backup settings. Then finish Gate E and Phase F within the reconciled allowance, avoiding repeated probes whose contracts have already passed.
5. Prove representative real company collection, both shortlist categories, portal explanations and the scheduled digest on the owner's device. Close private ingress, browser and deployed recovery/timer gates before release readiness.

Verdict: progress is real and the app has moved beyond mocked-only AI contracts. The current isolation completion claim should be narrowed, not used to enable fetching. The next blocker is reliable proof of a working, confined collection path; the project is not yet release-ready.

Fresh review verification: runtime-config tests 3/3 passed (0.300s); isolation-enabled preflight gap reproduced offline; egress false-positive reproduced with a mocked Docker exit 125; modified runner/launcher/preflight files compile and project Ruff lint passes. Aggregate ledger reconciles at 19 attempts/US$0.000836348/zero held. No live API/network/container checks or full backend/browser suites were rerun, and no implementation or commit was made.

## R1 implementation outcome — 2026-10-10

The owner assigned implementation and excluded Docker migration. The project-local solution moves NNP activation to `setpriv --no-new-privs` inside the already-attached AppArmor profile. Docker startup NNP stays true by default; the explicit Snap setting is `DOCKER_NO_NEW_PRIVILEGES=false`. All service and health-check payloads are wrapped, and affected proxy/ntfy/backup/restore helpers share the effective setting. This supersedes the earlier instruction to preserve Docker's pre-transition flag unconditionally.

Real disposable tests on Snap server 29.8.0 show `docker-default (enforce)`, payload `NoNewPrivs: 1` and successful service execution; startup compatibility does not require removing application NNP or migrating the daemon. Docker's initial trusted launcher/init and arbitrary Docker exec sessions remain outside the payload inheritance, so the solution is not identical to Docker-wide startup NNP. The default profile and other configured isolation controls remain intact. Deployment activation, administrative exec guidance and rollback are in DEPLOYMENT.md; actual evidence and remaining limits are in VALIDATION.md and PROGRESS.md.

The DNS/proxy candidate still needs the actual network-boundary matrix. This runtime fix does not authorize fetching enablement, private ingress changes or paid model calls.

## Current agent continuation review — 2026-10-09, baseline `72cb6df`

Purpose: give the implementing agent a concrete way to identify, remove and verify the current blockers. This is advice and source review only. It does not authorize host changes, installations, paid calls or implementation. Earlier reviews below are dated history; use the resolution status here before acting on them.

### Main judgment and order of work

The project has two independent deployment blockers. First, the recorded target runtime fails to start tested containers when `no-new-privileges` is enabled. Second, the fetcher's internal-only topology cannot provide the public DNS lookup required before proxied collection. Fixing either alone will not make the app collect jobs. Matching has improved offline, but useful live matching and the full deployed journey remain separate acceptance gates.

Work in this order: establish the actual runtime/host and diagnose its execution failure; demonstrate the production hardening flags work; choose and prove a restricted DNS/fetch path; then resume the remaining real schema, semantic and integrated journey checks. Prepare DNS ideas and offline fixtures while runtime access is unavailable, but do not substitute more optional product work for the blocked runtime gate.

### Blocker map: what fails, why, and what counts as closed

| ID | Observed or recorded failure | Cause status | Closure evidence |
| --- | --- | --- | --- |
| R1: container execution | Target-host records: `docker run --rm --security-opt no-new-privileges:true alpine:latest echo OK` fails with `exec /bin/echo: operation not permitted`, exit 255. Control without NNP succeeds. Several image/user/security-profile variations reportedly reproduce the association. | NNP is the changed variable in the recorded controls. Snap/AppArmor domain-transition denial is suspected; no correlated kernel audit evidence is recorded. | A minimal cached-image test and representative actual project services start with the required NNP/non-root/capability/read-only flags, on the intended daemon. Explain the fix and preserve the security boundary. |
| N1: public DNS before fetching | Recorded no-rule tests: internal service lookup succeeds, external lookup returns SERVFAIL in the tested internal-only topology. `resolve_public()` performs that external lookup before proxying. | An application/topology incompatibility is established by the recorded tests. The exact installed Docker behavior should be tied to the identified runtime, not generalized to every host/version. | Public DNS works through the chosen restricted path, proxied HTTP/HTTPS succeeds, and direct/private/bypass paths fail against controlled live listeners. |
| A1: reviewer runtime access | Fresh read-only `docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'` exits 1: permission denied at `unix:///var/run/docker.sock`. Client reports 29.1.5; server is unreadable. | This review session lacks daemon access. It is not the target EPERM result, and a client version alone does not identify the server/package. | The implementing agent uses the already-authorized intended runtime, or obtains the exact required read-only/privileged execution from the owner. Do not change socket permissions or group membership just to complete this review. |

R1 affects the Compose runtime broadly: `x-runtime` supplies NNP to the database, application services and supporting services, while `scripts/check-proxy.py` also supplies it explicitly. A failing Squid process under those flags never reaches DNS or ACL evaluation. Classify that as startup failure, not proxy policy rejection or a collection result.

### Instructions to the agent: diagnose R1 before prescribing a host fix

1. **Establish identity and scope.** Record the intended host, active Docker context, client/server versions, daemon package, kernel version, effective security profiles and the exact image digest used for the failure. Keep output narrow and sanitized; do not dump unrelated containers, environment variables, secrets or full daemon configuration. Explain whether the older daemon/version entries concern a different host or an earlier state.
2. **Keep the existing control evidence.** The recorded failing NNP test versus successful non-NNP test is useful. Avoid another sweep of unconfined/privileged/root combinations. If one fresh correlation is needed and authorized, use an already-cached digest, no pulls, no network, a uniquely named disposable container and a bounded command; record timestamp, exit status, creation/start state and cleanup. A flag-free control is diagnostic only, never deployment acceptance.
3. **Correlate kernel evidence.** Request narrowly filtered kernel/audit lines for the exact failure interval and executable. For example, the owner can run `sudo journalctl -k --since '<failure start timestamp>' --until '<failure end timestamp>' --no-pager` and share only relevant, redacted denial lines. Obtain the timestamps first. The existing suggestion of the last 30 dmesg lines can miss the relevant event or show an unrelated denial. No matching audit record means the cause remains unresolved; it does not prove AppArmor is innocent or guilty.
4. **Separate daemon confinement from container profiles.** A failure surviving `apparmor=unconfined` in a container does not by itself rule out a confined daemon. NNP can affect Linux security-module transitions, but that general mechanism does not establish this host's diagnosis. The [kernel NNP documentation](https://docs.kernel.org/userspace-api/no_new_privs.html) describes inheritance and exec restrictions, including possible interaction with security-module sandboxing; [Docker's AppArmor documentation](https://docs.docker.com/engine/security/apparmor/) distinguishes container policy and daemon policy and describes kernel-log diagnosis. Neither source proves a Snap defect here.
5. **Present one evidence-backed remedy with rollback.** If audit/package evidence establishes a supported runtime-policy issue, identify the exact supported correction and its scope. If the intended host cannot safely run the required flags, propose using a compatible Ubuntu Docker runtime/host. Replacing the daemon is a host migration: inventory the owner's affected services and data, preserve them, describe downtime/rollback and obtain specific authorization before any action. Do not uninstall Snap, restart the daemon, patch AppArmor, change package routes or migrate volumes on assumption.
6. **Close R1 using the original boundary.** A fixed host must run the minimal NNP reproduction and representative actual project image commands with the complete production hardening. Verify running/healthy state and cleanup, not just Docker accepting a create request. A different working host closes the gate only for that host; it does not fix the original one.

Do not remove `no-new-privileges`, use host networking, disable confinement or add privilege to make checks pass. No application-code patch can be claimed to fix a daemon execution failure without demonstrating the changed execution path. A supported host remediation may be needed; its exact form is not known yet.

### Instructions to the agent: design and prove N1

The app needs public-name resolution because `backend/app/fetcher/http.py:resolve_public()` checks that URL destinations are global before proxying. Squid independently checks addresses at connection time. Docker service discovery is also needed for `egress-proxy`. Keep these separate from CV/model requests and from private ingress DNS.

1. **Write a short connection diagram before editing.** Name who resolves a public employer hostname, which resolver receives it, who makes the HTTP/TLS connection and where non-global destinations are rejected. Include internal service lookup, redirects and IPv4/IPv6. This exposes any unexpected direct route before rules are added.
2. **Compare the existing three options, then choose one.** A restricted non-internal fetch bridge restores a possible forwarding route but changes the boundary and conflicts with current installer/preflight assertions. A dedicated resolver adds a service and a specific allowed query path. Proxy-side resolution may be smaller but changes the role of the local precheck. Select using demonstrated behavior and smallest complete change; the owner should not have to design this for the agent.
3. **For a non-internal bridge proposal, account for every new route.** Update the design together with Compose, `deploy/fetch-control-rules.sh`, its internal-network preconditions and `scripts/check-deployment.py`. Prove the chosen resolver cannot be used to bypass the direct-egress restriction. Include host, worker/core, LAN/tailnet, cross-bridge, IPv6 and non-HTTP traffic; an IPv4 rule count alone is insufficient. Do not change production networks before a disposable proof and appropriate scoped approval.
4. **For a dedicated resolver proposal, specify the permitted destination and protocols.** Permit only the demonstrated resolver query path, define upstream behavior and prevent it from becoming a general relay into private networks. Do not allow port 53 to arbitrary destinations. Respect the dependency-failure boundary before introducing an image.
5. **For proxy delegation, prove equivalent destination enforcement.** Read the HTTP redirect loop and Squid ACL behavior first. Demonstrate public HTTP/HTTPS, private targets, literal/mapped IP forms and rebinding/private redirects at connection time. The local precheck's removal is a consequential security change, not a one-line workaround. Browser subresources must later use the same boundary.
6. **Use one disposable acceptance topology.** Pass the actual hardening from R1, correct/incorrect RPC tokens, internal service lookup, external resolution where required and a successful proxied request. Establish controlled forbidden listeners as reachable before enforcement and alive afterward. Preserve probe output/status; distinguish timeouts/denials from a failed probe process.
7. **Require a working positive path for closure.** The current harness accepts external DNS remaining blocked if that matches the baseline. That can diagnose rules correctly while collection is unusable. Report baseline-preservation separately; the fix's acceptance must include the real `resolve_public`/proxy/fetch path and the complete section 9.2 matrix. The planned `scripts/test-fetch-isolation.py` is still absent: implement or explicitly supply the smallest real acceptance runner when assigned, rather than directing the owner to a nonexistent command.
8. **Enable only after evidence, with consistent configuration.** Keep repository fetching disabled. After the required matrix passes, prepare the reviewed deployment override, corresponding preflight behavior and shared startup/backup/restore configuration. A passing disabled-template check does not authorize arbitrary fetches.

### What the latest matching fixes actually resolve

Fresh isolated source/domain checks on `72cb6df` confirm:

- A duty after character 3,500 is now included in the candidate pool. A 26,000-character synthetic unbroken span exceeds the explicit 50-chunk budget and raises instead of silently dropping evidence.
- Both known focus-domain outcomes with insufficient support now raise. Genuinely unknown remains a distinct judgment.
- A supported connection can cite selected profile skill evidence. The old unconditional connection citation of aggregate experience has been replaced.

These are genuine corrections. The recorded full backend result is 330 passing tests; this review did not rerun that database suite. Interpretation tests supplied synthetic answers; they do not demonstrate that Jev selects meaningful support on real inputs. Keep live Gate D open.

### Remaining implementation concerns for the next assigned batch

1. **Scoring still cites years rather than the selected overlap evidence.** In `decisions_adapter`, `score_evidence` remains the primary duties quotation plus `cite_span("profile:experience")`. That span holds aggregate experience bounds. For a score based on strategic-planning skills, the quotation of years does not substantiate the overlap. Idea: use a small explicit profile/intent evidence selection for score support, reuse the existing candidate mechanism, and manually verify support in the semantic set. Do not add another model or loosen provenance checks. Connection selection fixed only the connection half of the prior finding.

2. **The latest interpretation changes did not change assessment identity.** `4959867` and `72cb6df` both use `POLICY_VERSION="broad-v2"` and `matching-decisions-v2`, although the latter changes required connection support and domain/evidence rejection. `services/matching.py:saved`, `current` and `enqueue` reuse results/intents under that unchanged identity. Concrete case: an assessment saved by the previous adapter can remain current after upgrading to the stricter adapter; changing only prompt provenance would not invalidate it. Idea: advance the existing identity used by persistence/reconciliation for the finalized semantics and exercise the existing stale-result/reassessment tests. No new version registry is required. This is a correctness concern even if no live real-job assessment has been accepted yet.

3. **Candidate overflow loses its actionable explanation in the operation flow.** Overflow now raises `ValueError` before `infer()` in `assess()`. `services/operations.py` maps non-`OperationError` exceptions to generic `processing_failed` with a suggestion to retry or upload a document. For a job assessment exceeding the candidate budget, retrying the unchanged job cannot help. Idea: map this known local size refusal once at the task boundary to a stable, sanitized size/scope error, and verify operation state, visible message and zero provider requests. Preserve global unexpected-error redaction. Never paste raw source text or exception payloads into logs/UI.

4. **A failed proxy start can leave a named disposable container.** `scripts/check-proxy.py` sets `started=True` only after `docker run -d` returns successfully and cleans up only when that flag is true. If Docker creates the uniquely named container but its start fails under R1, cleanup is skipped. Idea: check/remove only that exact run-owned name after either creation or failed startup, preserve the original failure, and add a small mocked create-then-start-failure regression. Do not bulk-remove failed containers or touch unrelated services.

5. **Static validation does not enforce every claimed hardening flag.** `scripts/check-deployment.py:check()` rejects host networking and privileged services but does not assert NNP. Removing the runtime flag to bypass R1 could still pass that static checker. Idea: add a focused unsafe-configuration case for missing NNP and retain runtime verification of the full flags. A template assertion alone does not diagnose R1 or prove isolation.

6. **Boot persistence and stale addresses need actual lifecycle evidence.** `deploy/jobfinder-fetch-control.service` starts after Docker but has no dependency on the application containers becoming ready. It uses their current addresses and remains active after success; a later recreation can make those addresses stale without automatically rerunning the oneshot. The existing installer detects drift when invoked, but systemd ordering alone does not invoke it on every recreation. Idea: specify the exact app-start/recreate sequence and prove rules are reverified before fetching is enabled, including reboot/recreation. Keep this as an explicit deployment gate, rather than installing the unit and declaring persistence complete.

These concerns should be addressed in focused batches after R1/N1 investigation, with the checks needed for each change. They are not reasons to restart the architecture or add unrelated configuration/recovery features.

### What to ask the owner, and what the agent should handle

The immediate missing input is narrowly scoped **host/runtime evidence or access**, if the implementing agent cannot already read it: exact failure timestamps, relevant redacted kernel/audit records and intended daemon/package identity. The agent should first use its existing authorized read-only access. Do not request a sudo password, full logs, another CV/key or a higher AI budget to fix R1/N1.

After diagnosis, ask for approval only for the concrete host change or privileged harness execution that existing authorization does not cover. Explain the affected services, preservation/rollback plan and why that action is necessary. The parent guide requires scoped host-change review; do not infer permission to replace Docker or alter unrelated containers from general project-local build/run authorization. If a failed package/image fetch occurs, stop that setup path and report its original error; do not switch registries or retry without new instructions.

The agent should decide the restricted DNS design, prepare files/tests and make the proposed changes reviewable before requesting final host installation approval. The owner does not need to choose A/B/C in advance. The current review assignment is not permission to execute any of these fixes.

The latest user-provided AGENTS.md repeats the cumulative US$1/60-request ceiling, whereas older register entries call the dollar amount advisory. Treat the current explicit instructions as controlling, carry forward known/held accounting across phases and do not increase/reset the allowance. No paid validation is required to resolve R1/N1. Any genuinely necessary budget-policy clarification belongs before a later paid batch, not in the DNS diagnosis.

### Required handoff after each investigation batch

Update PROGRESS.md and actual check evidence in VALIDATION.md with: the host/runtime being tested; exact command and image digest; sanitized result/exit status; observations versus hypotheses; changed files/resources; cleanup/rollback outcome; blocker status; and one concrete next action. Keep one current snapshot and mark superseded findings historical.

Use precise labels: R1 runtime startup passed/failed; N1 DNS positive path passed/failed; real isolation matrix passed/failed; matching offline contract passed/failed; live semantic acceptance pending/passed/failed. Do not replace these with one “all tests pass” statement. Do not repeat failed host probes without a new hypothesis/evidence change, and do not continue optional feature work as a substitute for the blocked gate.

Verdict: preserve the recent fixes, diagnose the runtime failure first, then prove a restricted DNS/fetch path. Matching still needs the specific provenance/identity/error-path corrections above and live acceptance. The app remains unverified for deployment.

Fresh review checks: 7 mocked installer tests passed (2.126s); shell syntax passed; isolated matching checks confirmed the three corrections and remaining mechanical score evidence. Docker metadata access failed with socket permission denial. No daemon startup reproduction, audit-log read, dependency operation, container/host mutation, live request or full backend/browser suite occurred. This review is uncommitted.

## Historical follow-up review — 2026-10-09, baseline `4959867`

The latest changes make useful progress: the speculative DNS exceptions are gone, the mocked installer regression is fixed, partial-install rollback is exercised, and the matching adapter now evaluates domain fit and uncertainty. The DNS blocker remains open. Its cause is better understood, but no restricted resolver path has been implemented and demonstrated. The project is still awaiting real collection, matching and deployed-digest acceptance.

This follow-up was requested without a commit. It inspects the latest source and records fresh offline checks; it does not install rules, change topology, read secrets, make provider calls or reproduce the host DNS experiments. Earlier reviews below are preserved as historical evidence and must not be treated as current findings without the status updates here.

### Status of the earlier findings

| Earlier finding | Current status and evidence |
| --- | --- |
| 1. Installer count regression | Resolved in the current source. The rule set and expectations are back to `8 2`. Fresh `python3 scripts/test_fetch_rules.py`: all 7 tests pass, exit 0, 2.187s. This proves mocked installer behavior, not host enforcement. |
| 2. Speculative DNS attribution | Attribution has improved. PROGRESS.md and VALIDATION.md report external DNS returning SERVFAIL on an internal-only network before rules, while internal service-name lookup works; ordinary and dual-homed non-internal bridge cases resolve external names. The resolver path needed by the application is still unresolved. |
| 3. Incomplete Jev conversion | Substantially improved offline: five-anchor scoring, exact quotation candidates, dynamic focus-domain/uncertainty judgments, comparability and separate sufficiency are present. The recorded 329-test backend pass was not rerun here. Two fresh counterexamples below mean this finding is only partially resolved; the live Phase D gate is also still open. |
| 4. Conflicting current-state records | Improved: a top-level authoritative snapshot and matching budget statements now exist in the decision register and API companion. README.md still describes private-registry lock migration as pending, and AGENTS.md still states the original cumulative ceiling while later records describe an advisory dollar cap. Reconciliation is not complete across all active guidance. No changed spending authorization is inferred by this review. |
| 5. Unfinished gates | Explicitly acknowledged as open. That resolves the reporting concern, not the actual schema, semantic, isolation, device-delivery or recovery gates. Calling the adapter “Phase D completed” should mean offline implementation only, because Gate D includes a useful live assessment. |
| 6. Partial-install failure coverage | Improved and independently rerun: the fake fails on the fifth insert after four successful inserts, then checks cleanup. The harness now preserves more diagnostics and checks container/host-listener health, but those checks do not yet make a successful run proof that fetching works. |

### Current blocker and its boundaries

The fetcher is attached to `fetch_control` and `fetch`, both configured as internal networks. Its `resolve_public()` performs local DNS resolution and rejects non-global addresses before sending a request through Squid. The latest recorded host experiments show public-name forwarding unavailable through Docker's embedded resolver on the tested internal-only topology. As a result, normal public-site requests encounter `source_dns` before the proxy can fetch them.

This is an application/topology incompatibility to resolve, rather than missing candidate data, provider credentials or model choices. It is not evidence that the old TLS/dependency/VPN problem has returned. The recorded behavior applies to the tested daemon/topologies; this review does not independently prove a universal Docker behavior or the cited Moby source attribution.

The speculative INPUT exceptions aimed at `127.0.0.11` have correctly been removed. Retrying the unchanged topology or allowing arbitrary port-53 traffic would not constitute a demonstrated fix.

The next implementation task is to select one restricted DNS path and prove both successful public resolution and retained isolation. The agent should compare the smallest feasible choices using the existing Squid boundary:

- A carefully restricted non-internal fetch bridge may restore embedded forwarding, but the current installer explicitly requires both networks to be internal. Changing Compose alone cannot implement this option; enforcement, installer preconditions and the real bypass tests must change together.
- A dedicated restricted resolver retains the internal fetch bridge but adds an operational service and must have a demonstrated, destination-scoped query path.
- Delegating resolution and destination enforcement to the proxy could avoid another service, but removing the local precheck requires proving equivalent protection at actual connection time, including redirects and private-address/rebinding cases.

These are design options, not approved or validated solutions. Choose by evidence and smallest complete change. Keep fetching disabled until the positive and negative paths pass.

### Remaining mistakes and concerns

1. **A green diagnostic harness can coexist with the DNS blocker** ([scripts/test-fetch-control-harness.sh](scripts/test-fetch-control-harness.sh), external DNS baseline and final result).
   - **What this is:** The harness now expects post-rule external DNS to match its pre-rule baseline, including a blocked baseline.
   - **Problem:** External DNS blocked before and after rules is useful attribution evidence, but can produce `HARNESS PASSED` while the real fetcher still cannot resolve a public employer. Container-running checks also do not establish that every listener process remains healthy, and exit 1 still covers more than an intentional network denial.
   - **Fix:** Keep the baseline diagnostic, but distinguish “rules preserve baseline behavior” from “fetch topology usable.” The acceptance run for the chosen fix must require working external resolution and actual proxied HTTP/HTTPS, retain negative-path diagnostics and establish listener health. The full isolation runner referenced as `scripts/test-fetch-isolation.py` does not currently exist; the agent must supply that acceptance path rather than ask the owner to run a nonexistent file.
   - **If we skip it:** The agent can mark a harness green without removing the collection blocker. This is an acceptance/reporting risk, not evidence that rules are installed on the real stack.

2. **Evidence candidates silently stop before the end of valid listings** ([backend/app/ai/matching.py](backend/app/ai/matching.py), `extract_evidence_candidates`).
   - **What this is:** The candidate loop stops at six chunks of at most 500 characters per span. Descriptions can contain up to 200,000 characters, and paragraph splitting can make the represented prefix shorter than 3,000 characters.
   - **Problem:** A fresh isolated-source self-check used a valid 3,522-character description with a duty at the end. That duty was absent from every selectable candidate, without any size/scope error. The full span remains in state, but the model cannot select the required exact evidence when it occurs beyond the candidate prefix.
   - **Fix:** Cover the accepted span within an explicit candidate/request budget or fail visibly when complete coverage cannot fit. Do not silently truncate the candidate pool. Add one regression beyond the six-chunk boundary; the existing 1,500-character late-evidence test does not exercise this case.
   - **If we skip it:** Real postings can lose their decisive duties or requirements from explanations and be assessed using incomplete evidence. The documented claim of complete bounded candidates is stronger than the implementation.

3. **An unsupported known domain judgment is converted into a successful unknown** ([backend/app/ai/matching.py](backend/app/ai/matching.py), focus-domain interpretation).
   - **What this is:** If Jev returns `domain_status="not_met"` or `"met"` with `domain_evidence="insufficient"`, the adapter changes the domain result to unknown.
   - **Problem:** A fresh synthetic self-check supplied an aligned high-scoring role, a known domain conflict and insufficient supporting evidence. The interpreter returned a valid unknown-domain `possible_match`, rather than rejecting the contradictory/unsupported assessment. All requested answer keys were supplied; this is not a missing-wire-field case.
   - **Fix:** Preserve genuinely unknown judgments, but reject known outcomes lacking the selected support, as the criterion branch already does. Add a small regression for both known domain outcomes with insufficient evidence before live semantic acceptance.
   - **If we skip it:** Unsupported responses can be recorded as successful assessments, concealing a model/evidence failure and weakening focus-domain handling.

4. **Score and transfer evidence still relies on mechanically chosen excerpts** ([backend/app/ai/matching.py](backend/app/ai/matching.py), `score_evidence`, `connection_evidence`, `cite_span`).
   - **What this is:** The score and connection cite the selected duties candidate plus the first 500 characters of `profile:experience`; preference intent is likewise cited from a prefix rather than separately selected support.
   - **Problem:** `profile:experience` describes experience bounds, not the reviewed responsibilities and skills that might support a transferable connection. A role can be judged transferable because of a skill elsewhere in state while the displayed candidate-side quotation contains only experience totals. Exact-substring validation proves provenance, not the claimed relationship.
   - **Fix:** Include suitable candidate-side evidence selections in the existing typed request and check the supporting meaning in the small semantic set. Keep the original professional-data privacy boundary; do not add a second explanatory model call.
   - **If we skip it:** Matching may produce valid schema and quotations while the explanation fails to support its score or connection. This remains a matching-acceptance concern independent of DNS.

### Inputs needed from the owner

No additional CV, API key, model selection, paid budget or employer list is needed to investigate and implement the DNS fix. The agent can choose the technical approach, prepare the exact topology/configuration changes, tests and rollback, and validate everything within existing local authority. The owner need not choose among networking options on the agent's behalf.

The only likely owner involvement for this blocker is **privileged execution or scoped host-change authorization**. The parent guide, FINISH_DEVELOPMENT_AND_VALIDATE.md sections 1 and 9, requires concrete scoped firewall/host changes to be reviewed where authorization is not already granted. Earlier approval for a particular disposable harness is not necessarily approval to install a changed policy on the real stack. If the agent cannot run the revised privileged harness, it should provide the exact reviewed command and ask the owner to run it, with sanitized output and exit status. Do not request passwords in chat or a blanket firewall/VPN/Docker-daemon change.

A suitable continuation instruction is: “Resolve the fetcher DNS blocker using the smallest demonstrated restricted path. Prepare the changes and rollback, test them on disposable resources within existing authorization, and keep production fetching disabled. Ask me only for any specific privileged execution or new host change not already authorized. Do not add optional features or make unrelated network changes.”

That instruction assigns implementation; this review itself does not start it. Real-stack installation approval should follow a concrete, reviewable fix and successful disposable checks. If the agent still reports that it needs owner input, it should name the exact missing permission or host constraint; “choose a DNS design” is not sufficient.

Later deployment gates may separately need LAN/tailnet hostnames, client trust, notification-device access and backup destinations. Those are not prerequisites for diagnosing this DNS blocker.

Verdict: the original installer regression is resolved, DNS attribution is materially better, and offline matching has improved. The blocker is narrowed but not removed; remaining evidence/interpretation defects prevent declaring matching complete. Continue focused acceptance work rather than expanding scope.

Fresh checks: 7 mocked installer tests passed; shell syntax passed; isolated source/domain self-checks reproduced candidate truncation and unsupported-domain normalization, both with synthetic inputs and no provider imports or database/network/state access. Full backend/browser suites, actual host DNS/firewall enforcement, live matching, private ledger contents and deployed delivery/recovery were not rerun. No commit was made for this follow-up.

## Historical execution review — baseline `594b1ab`, saved as `0aeb034`

What this change does: This review assesses the work recorded through 2026-10-09, including the deployment-host continuation, first live API probes and fetch-isolation attempts. It updates the earlier architectural assessment with concrete implementation findings and a proposed next acceptance sequence.

Review baseline: `594b1ab`, plus existing uncommitted changes in `deploy/fetch-control-rules.sh` and `scripts/test_fetch_rules.py`. Expected workload is one owner, one active candidate profile and selected-company monitoring. This is a progress and approach review with sampled code inspection, not a whole-repository security audit. Recommendations do not authorize implementation, host changes or further paid calls.

## Assessment

There is substantial implemented work and credible local validation. The project is closer to deployment than the older summaries suggest, but it has not demonstrated its central benefit: real vacancies collected safely, assessed usefully and delivered in a scheduled digest to the owner. Release readiness remains unproven.

The previous review's concern about sequencing still holds. However, moving to the intended host, validating dependency portability, completing a disposable restore drill and testing the real provider transports are meaningful responses to it. The current isolation work addresses a required boundary, so it should be completed carefully rather than dismissed as optional complexity.

The clearest weakness in the latest attempts is changing the proposed fix before establishing the cause. The DNS failure was observed after firewall rules, but DNS was not tested before them. The subsequent exception is speculative and introduces an independently reproducible installer regression. Repeated advisory reviews improved the work, but basic execution-path and baseline checks should catch these defects before another privileged run.

## Progress and evidence

| Area | Evidence recorded or inspected | What remains unproven |
| --- | --- | --- |
| Product and architecture | Requirements keep CV history separate from future preferences, inventory separate from matching, and failures separate from empty results. The focused app reuses PostgreSQL for durable work instead of adding another broker. | Whether the resulting workflow saves the owner time with real vacancies. |
| Application workflows | Local API/database/worker/browser journeys cover profile review, inventory, explanations, settings and recovery. The historical record reports 11 browser journeys and 30 frontend tests passing. | These are synthetic/mocked-provider journeys, not final deployed-browser or model-quality acceptance. |
| Deployment-host setup | The record reports public-registry installs, preserved backend versions/hashes, frontend build/image smoke checks and a normal-bridge loopback PostgreSQL test service. | Full application Compose startup, private ingress, host/client trust and complete image/runtime acceptance. |
| Provider integration | Later records report 324 backend tests passing and two live synthetic probes: Luna chat and Jev Decisions. Recorded ledger: 2 attempts, US$0.000020042 known, no held spend. | Actual profile/extraction schemas, useful matching, authenticated Settings/queue integration and semantic evaluation. Request acceptance is not independent proof of provider-side privacy enforcement. |
| Fetch isolation | Shared rule application, marked rollback and disposable listeners are implemented. Owner-run harness reportedly passed five post-rule probes and failed external DNS. | DNS baseline, complete real-container safety matrix, IPv6/rebinding/browser containment and a safe enablement path. Compose still disables arbitrary fetching. |
| Notifications and recovery | Local notification-ledger/transport tests, isolated ntfy permissions and a disposable encrypted full-data restore are recorded. | Application-worker-to-ntfy delivery, owner's device receipt, installed nightly timer and deployed-application restore. |

Except for the mocked firewall tests below, these execution results are historical records from [PROGRESS.md](PROGRESS.md) and [VALIDATION.md](VALIDATION.md), not independently rerun results from this review. The tiny live probes are transport evidence only; Phase C's actual generative-schema checks and subsequent gates remain open.

## Must fix before the affected gate

1. **The current installer rejects its own rules** ([deploy/fetch-control-rules.sh](deploy/fetch-control-rules.sh), `apply_rules`, `install`, `verify`; [scripts/test_fetch_rules.py](scripts/test_fetch_rules.py)).
   - **What this is:** The uncommitted DNS edit adds four INPUT rules. It leaves eight DOCKER-USER rules but changes both expected counts to `12 6`.
   - **Problem:** Fresh `python3 scripts/test_fetch_rules.py` exits 1: six tests run, four fail. Install reports `expected 12 DOCKER-USER and 6 INPUT managed rules, found 8 6` and rolls back; reinstall and drift checks consequently fail too.
   - **Fix:** Restore the pre-exception rule set and matching `8 2` expectations as already proposed in the DNS checkpoint. Rerun the mocked installer suite before another harness attempt; changing the count to `8 6` alone would retain the unproven exception.
   - **If we skip it:** The installer cannot establish the intended policy, even if direct harness calls to `apply_rules` appear successful. No real firewall was changed by this review.

2. **The DNS fix has no demonstrated causal basis** ([scripts/test-fetch-control-harness.sh](scripts/test-fetch-control-harness.sh), lines 114–140; [backend/app/fetcher/http.py](backend/app/fetcher/http.py), `resolve_public`).
   - **What this is:** The harness establishes five TCP baselines but tests `nslookup example.com` only after rules. The real fetcher resolves public names before sending its proxied request.
   - **Problem:** A failed post-rule lookup cannot distinguish a firewall regression from DNS already failing on an internal-only Docker topology. Host INPUT exceptions aimed at `127.0.0.11` do not demonstrate a working path to Docker's resolver in the container namespace.
   - **Fix:** Remove the speculative exception, then test external-name and internal-service-name resolution separately before and after rules on the installed Docker version. If the topology itself prevents required public resolution, choose and demonstrate a restricted resolver path while retaining the destination checks; do not widen port-53 access on speculation.
   - **If we skip it:** The real collector can still fail with `source_dns`, or isolation can be weakened without making collection work. The Moby explanation in the progress record is a hypothesis for this host until the baseline confirms it.

3. **The Jev adapter is a transport-stage implementation, not complete matching** ([backend/app/ai/matching.py](backend/app/ai/matching.py), `decisions_adapter`; [backend/app/domain/matching.py](backend/app/domain/matching.py), `category`).
   - **What this is:** The conversion always writes `important_unknowns=True` and `domain_status="unknown"`. It cites the first 1,000 characters of selected spans and uses four mapped scores, `[15, 40, 60, 85]`.
   - **Problem:** An aligned role with a high score and fully known requirements can never become `match`. A clearly conflicting focus-domain role is never rejected on its domain conflict. A duties sentence later than character 1,000 can be selected via its whole span while the displayed quotation omits that sentence. Exact-substring validation does not prove that the quotation supports the judgment.
   - **Fix:** Complete the existing Phase D work: explicit domain/uncertainty judgments, bounded exact evidence candidates and a tested relevance conversion. Reconcile the four-band implementation with the documented five-anchor mapping before semantic tests; do not silently change the broad-shortlist policy or remove unknown handling.
   - **If we skip it:** Strong and uncertain fits collapse into Possible, focus preferences are not fully honored and explanations can cite irrelevant text. Keeping both categories in the digest preserves broad browsing, but does not satisfy matching acceptance.

## Should fix

4. **Current-state documents disagree with completed work and spending decisions** ([PROGRESS.md](PROGRESS.md), “Current state”; [README.md](README.md); [DECISIONS.md](DECISIONS.md); [DEPLOYMENT_API_VALIDATION.md](DEPLOYMENT_API_VALIDATION.md)).
   - **What this is:** Later checkpoints record deployment-host setup and two paid probes. Older active-looking summaries still say zero inference requests, unchanged private-registry locks and a planned Jev adapter. The progress log and launcher describe the dollar cap as advisory following a recorded owner revision, while active guidance still states a cumulative ceiling.
   - **Problem:** A successor using those summaries can repeat completed setup, start accounting from zero or apply an inconsistent spending gate. The review cannot independently establish the intervening authorization from Git records alone.
   - **Fix:** Make one top-level current snapshot authoritative and label superseded entries historical. Reconcile the confirmed budget requirement across the decision register, companion and launcher before the next paid batch; carry forward the two recorded attempts and known spend, then compare with the durable ledger. This review grants no budget change.
   - **If we skip it:** Handoffs keep rediscovering state and may spend or retry under obsolete instructions. Document links and long logs cannot compensate for a wrong current summary.

5. **Success at one validation layer is being used to move past unfinished gates** ([DEPLOYMENT_API_VALIDATION.md](DEPLOYMENT_API_VALIDATION.md), Gates C–F; [FINISH_DEVELOPMENT_AND_VALIDATE.md](FINISH_DEVELOPMENT_AND_VALIDATE.md), sections 8–11).
   - **What this is:** Work moved from tiny successful transport probes to isolation preparation while the actual generative schemas, matching semantics and integrated provider journey remain pending. Isolation is independently necessary, but section 8 is not complete.
   - **Problem:** More implemented mechanisms and passing local tests still leave the owner without evidence that the app can collect and shortlist useful real jobs. Generic `ok` probes cannot establish acceptance of the nested profile/extraction schemas.
   - **Fix:** Keep unfinished gates explicitly open. Finish the current DNS/isolation blocker, complete the missing schema/semantic checks within the reconciled allowance, then prove one reviewed-profile → representative real collection → broad matching → portal → scheduled device digest journey. Defer new capabilities and optional polish; retain the required difficult-source and full safety/recovery gates.
   - **If we skip it:** Further engineering can accumulate without resolving whether the delivered product works. No rewrite or removal of existing recovery guarantees is justified by this review.

6. **The mocked transaction test does not exercise a partial installation failure** ([scripts/test_fetch_rules.py](scripts/test_fetch_rules.py), `FAKE_IPTABLES` and `test_apply_failure_rolls_back_partially_installed_rules`).
   - **What this is:** In `fail-inserts` mode, the fake iptables command rejects every insertion, starting with the first one.
   - **Problem:** The test described as partial rollback creates no rules before failure. It would still pass if cleanup left already-inserted rules behind. The harness also classifies every nonzero probe exit as “blocked,” so a failed `docker exec` can resemble successful network denial.
   - **Fix:** Add one offline case that fails after several successful insertions and verifies removal of only this run's marked rules. Preserve probe diagnostics and check execution/listener health before accepting negative network results; do not add a new test framework.
   - **If we skip it:** The rollback claim is stronger than its test evidence, and privileged safety checks can report false success when their probes fail to execute.

## Assessment of the attempts

| Attempt | Assessment and lesson |
| --- | --- |
| Original dependency/TLS and Docker bridge failures | Recording exact failures and separating routing observations from suspected causes was sound. The development-only host-network database exception did not prove production isolation. Later owner-authorized public-registry/normal-bridge work is separate evidence, not permission to retry canceled development-network probes. |
| Broad mock-first implementation | Useful for data integrity, stale-result protection, durable scheduling and UI recovery. It also allowed substantial breadth before source/model usefulness was measured. Authored responses establish orchestration, not model quality. |
| Backup and restore following the prior review | A concrete improvement: the disposable drill exposed a real helper-permissions defect and the recorded rerun passed. Deployed recovery and scheduling still need their own evidence. |
| Decisions adapter and spending harness | Reusing existing task/accounting paths was appropriate. Advisory review caught bypassed domain validation and unbounded-charge assumptions; production-path tests improved the design. A reservation limits admissions, not the provider's eventual charge, so the spending limitation must remain explicit. |
| First live Luna/Jev probes | Correctly small and synthetic, with recorded versions, costs and cleanup. They uncovered a real pricing-metadata compatibility defect. One accepted request per protocol does not establish application schemas, semantic usefulness or privacy enforcement beyond externally visible routing/acceptance. |
| Stateful firewall preparation | Correctly recognized that shared internal networks do not enforce connection direction and that host traffic needs INPUT coverage. Missing protocol, per-network addressing, idempotency and persistent-listener defects were caught and corrected. Those findings justify running basic offline checks before asking the owner to run privileged tests. |
| First isolation harness and DNS response | The five TCP baselines improve the negative-test evidence. Missing DNS baseline prevented attribution; the exception was added before proof and its counts were not checked. Stopping and recording uncertainty was the right recovery. The exception is still present in the reviewed uncommitted files. |

## Recommended continuation

1. Preserve the owner's uncommitted work and make the review findings concrete in the next authorized implementation task: restore the pre-exception rules and pass the mocked installer checks.
2. Establish DNS baselines, then demonstrate any necessary resolver path in the disposable topology. Complete the real isolation matrix before enabling arbitrary fetching.
3. Reconcile current-state and budget documents with the durable accounting record. Continue the missing actual-schema, Jev evidence/policy and small semantic acceptance cases; no new paid call is authorized by this review.
4. Prove the complete journey with a small representative company set, including one difficult source. Verify private deployed access, scheduled device delivery and deployed restore/timer operation before claiming release readiness.
5. Choose further improvements from measured failures and owner feedback. Keep the stack and existing guarantees; adding another framework or rewriting the queue would not resolve the present gates.

Verdict: fix 1–3 before passing the affected deployment/matching gates. Record 4–6 before relying on the next handoff and safety-validation results. The application is not ready to ship.

Not checked: full regression/browser suites, actual host firewall/DNS behavior, provider/privacy contracts, private ledger contents, real collection, device delivery and deployed recovery were not rerun. No dependency operations, live requests, secret reads, runtime changes or implementation fixes were performed.

## Historical architectural review — 2026-10-08

The original review below is retained as dated context. Its pending-state statements and approximate code-size count are historical, not the current execution snapshot.

Review date: 2026-10-08.

This is a read-only architectural assessment of the project at the time of review, recorded at the user's request. It compares the original product intent with the current plan, progress record, Compose configuration, source structure and sampled implementations. It is not a full correctness or security audit. Tests were not rerun, and recorded validation results were not independently reproduced. Recommendations below are proposals, not approved changes to requirements or implementation scope.

## Overall assessment

The progress is real and generally disciplined, but the project is becoming heavier than a one-person job finder needs for its first usable release. There is some premature engineering. The bigger concern is how much has been built before proving the core benefit with real jobs.

This is a promising, carefully built application whose ambition is getting ahead of its demonstrated usefulness. The recommended response is to narrow the next acceptance milestone, not rewrite the application or add more architecture.

## Complexity that is justified

The requirements in [CONTEXT.md](CONTEXT.md) are more demanding than a daily scraping script: editable CV analysis, different company websites, broad explainable matching, persistent scheduling, private deployment and notifications. Some complexity follows directly from those requirements.

Several decisions look sound:

- Keeping collected jobs independent of matching protects manual browsing.
- Distinguishing collection failures from “no vacancies” prevents misleading results.
- Tracking profile changes prevents outdated assessments appearing current.
- PostgreSQL plus a database-backed queue avoids adding Redis or another broker.
- Fetch isolation has a concrete purpose: external websites should not reach private services.
- Authentication, bounded spending, backups and basic retry protection are reasonable even for one owner.

The progress record carefully distinguishes synthetic checks, real local database/browser tests and unverified live behaviour. That is good engineering practice. See [PLAN.md](PLAN.md) and [PROGRESS.md](PROGRESS.md).

## Areas of disproportionate or premature complexity

| Area | Assessment |
| --- | --- |
| Background execution | The application maintains its own operation states, leases, retries and recovery alongside Procrastinate's queue machinery. There are valid transactional reasons, but this is a substantial maintenance burden for the expected workload. |
| Provider accounting | Spending limits are useful. Detailed reservation recovery, billing reconciliation and dedicated recovery UI feel advanced before any live model has been accepted. |
| Extraction breadth | ATS adapters, JSON-LD, AI extraction, configurable CSS rules, previews and planned browser fallback collectively approach a general-purpose collection platform. Broader website support is required eventually, but the first release could prove a narrower path. |
| Recovery and configuration UI | Conflict handling and explicit errors are useful. Completing many advanced controls before observing actual usage increases the chance of polishing workflows the owner rarely needs. |
| Deployment | Ten Compose services and six networks are substantial for personal hosting. However, two services are one-shot setup jobs and several share an image, so describing this as ten independent microservices would be unfair. |

The most concrete simplification candidate is the interaction between [operation handling](backend/app/services/operations.py) and [queue dispatch/recovery](backend/app/tasks/worker.py). Review that boundary before adding more lifecycle states; do not remove existing recovery guarantees without understanding their purpose.

At inspection, the backend contained approximately 9,300 application lines across 63 Python files, excluding tests. Size alone does not establish overengineering, but this has become a meaningful application to maintain.

Other sampled implementation evidence includes [provider integration](backend/app/ai/provider.py), [matching policy](backend/app/domain/matching.py), [notification delivery](backend/app/notifications/delivery.py) and [Compose topology](compose.yaml). Sampling does not establish that every mechanism is necessary or correct.

## The strongest concern: order of work

The application has extensive local validation, but the decisive product questions remain open:

- Does it reliably collect the jobs the owner actually cares about?
- Does the chosen model produce a useful broad shortlist?
- Does the scheduled digest reach the owner's device?
- Can the owner install and operate it on the intended server?

Those questions could change the design more than another recovery screen or frontend optimisation.

The user deliberately deferred live model selection and paid validation, and the development network blocked other acceptance work. The agent was right to respect those boundaries and continue independent tasks. However, continuing to build peripheral features indefinitely is not necessarily the best response to blocked validation.

Much of this complexity was already selected in [IMPLEMENTATION.md](IMPLEMENTATION.md). This is partly an ambitious-plan problem, not simply an agent wandering outside scope. [DECISIONS.md](DECISIONS.md) distinguishes user requirements from selected implementation defaults; the latter remain candidates for reassessment.

## Recommended next milestone

Keep the existing work and make the next acceptance milestone smaller:

1. Freeze new capabilities and optional polish.
2. Complete a basic backup/restore path.
3. On the intended host, prove one complete journey: reviewed profile → real collection → real matching → portal → scheduled ntfy delivery.
4. Start with a few representative companies, including one difficult source; then expand to the agreed development examples.
5. Use observed failures to choose the next engineering work.

Live paid checks still require the user's authorization and model choices. Advanced features can remain implemented without making their further refinement mandatory for the first usable milestone. A narrower milestone does not silently remove the existing requirements or deployment acceptance gates.

The priority should be getting the application to help the owner find real jobs before investing further in sophistication.
