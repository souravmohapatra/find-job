# External engineering review

Review date: 2026-10-12. Baseline: `e6b1fa9` (clean working tree at intake).

This document is the sole requested write. Application code, configuration, databases, containers, credentials, and existing development records remain unchanged. No deployment, dependency operation, live provider request, or notification publication was performed. No commit was made.

## Scope and method

This is an independent source and development-evidence review of the personal Job Finder application. It covers architecture and stack selection, persistence and concurrency, profile privacy, collection/discovery, matching and cost controls, authentication, frontend behavior, notifications, deployment isolation, backup/recovery, and the reliability of the recorded acceptance evidence.

The review uses the current code and tracked configuration as implementation evidence, and the Markdown records as requirements, historical decisions, and reported validation. Historical test passes are not fresh execution evidence. The review does not certify the state of a running deployment or private local overrides. It deliberately avoids reading credentials, real CVs, and private runtime data.

The full backend suite is not appropriate for this read-only review: its autouse fixtures migrate/bootstrap and truncate a disposable database. Container, browser, live API, notification, and recovery runners also have side effects. Findings will distinguish source-proven defects, missing implementation, and remaining acceptance gates.

## Overall assessment

**The architecture is defensible, but this checkout is not ready for an unqualified “fully developed and ready for unattended use” sign-off.** There are concrete defects in the supported live deployment path, recovery, and validation tooling, as well as an explicitly planned collection capability that remains absent.

The central design is appropriate for a private, single-owner monitoring tool. Separate inventory and suitability data, immutable revisions, durable operation intents, conservative vacancy closure, and explicit notification ambiguity are strong choices. A rewrite is not justified. The priority should be completing and proving the existing product, with a smaller and more reliable operating surface.

I identified **18 review items: 4 High, 13 Medium, and 1 Low**. No Critical vulnerability or confirmed data loss was established. Absence of a Critical finding is not a security certification.

### Severity definitions

| Severity | Meaning in this review |
| --- | --- |
| Critical | Demonstrated immediate compromise, major irreversible data loss, or comparably severe failure. None established. |
| High | Prevents a core supported workflow or undermines a required security boundary. Resolve before enabling the affected unattended/live path. |
| Medium | Reproducible correctness, recovery, resource-control, usability, or acceptance-evidence defect with a bounded trigger. Resolve before depending on that behavior. |
| Low | Maintainability or documentation/tooling inconsistency without a demonstrated core runtime failure. |

“Confirmed” below means established by source tracing or an explicitly described isolated reproduction. It does not mean reproduced against the deployed application. Missing capability and acceptance-evidence findings are labelled separately.

### Finding index

| ID | Severity | Finding | Evidence type |
| --- | --- | --- | --- |
| ER-01 | High | Development validation ledger is mandatory for production inference and has no supported writable deployment path | Confirmed source/configuration defect |
| ER-02 | High | Selected native matching protocol cannot be configured through the portal or enabled by the shipped Compose parameters | Confirmed source/schema/configuration gap |
| ER-03 | High | Fetch isolation does not remain fail-closed across restart, recreation, or rule drift | Confirmed lifecycle/verifier weakness; exposure conditional on enablement |
| ER-04 | High | “Configuration check” can start a host-network, Docker-socket helper and install packages | Confirmed tooling side effect |
| ER-05 | Medium | Owner billing reconciliation leaves the cumulative spend reservation held | Confirmed source defect |
| ER-06 | Medium | Shared-ntfy change makes previously valid format-1 backups unreadable by current recovery tools | Confirmed compatibility regression |
| ER-07 | Medium | Explicitly expired generic vacancies remain active indefinitely | Confirmed lifecycle defect |
| ER-08 | Medium | Exhausted worker leases strand collection/profile state outside the operation table | Confirmed recovery defect |
| ER-09 | Medium | Upload size/authentication checks occur after multipart file spooling | Confirmed installed-framework reproduction |
| ER-10 | Medium | ntfy check can falsely certify publish permission and can publish while claiming not to | Confirmed mocked reproduction and upstream source |
| ER-11 | Medium | Live semantic/integration gate claims exceed what their harnesses assert | Confirmed acceptance-evidence gap |
| ER-12 | Medium | Browser-rendered collection is a planned but unimplemented capability | Confirmed missing implementation |
| ER-13 | Medium | Saving a matching model can trigger paid reassessment despite contrary UI copy | Confirmed source behavior |
| ER-14 | Medium | Promised operational-data retention is not implemented | Confirmed implementation gap |
| ER-15 | Medium | Worker failures and degraded dependencies lack the promised operational visibility | Confirmed implementation gap |
| ER-16 | Medium | Lever pagination bypasses the documented per-run page cap | Confirmed source defect |
| ER-17 | Medium | API field errors are discarded and several form errors are not associated with controls | Confirmed frontend defect |
| ER-18 | Low | Current-state documentation and static-check conventions have drifted | Confirmed metadata/tooling inconsistency |

## Architecture and design review

### Choices worth retaining

**React/Vite and FastAPI fit the product.** A private application without public indexing does not need server rendering. The UI has sensible route splitting, same-origin requests, a small navigation hierarchy, and no need for a WebSocket infrastructure. Python is a reasonable integration language for documents, structured extraction, and source adapters.

**PostgreSQL plus Procrastinate is justified.** The application needs concurrent workers, transactions, scheduling, history, and recovery. Reusing PostgreSQL avoids a separate broker. The business-operation/outbox layer has a real purpose because ORM writes and queue insertion use different connections. Stable IDs, uniqueness, row locks, and leases address duplication and stale completion. This is appropriate at the current scale, although the two overlapping lifecycles demand careful recovery tests (ER-08).

**The domain model follows the important requirements.** All-jobs queries start from inventory rather than a matching result; the shortlist includes both categories; experience and future preferences are separate; domain labels and desired functions are user-defined; profile/job/configuration/policy/mode identity protects current assessment views. No strategy-specific production eligibility rule was found. Feedback is stored without silently altering preferences.

**Matching has a useful deterministic boundary.** Models supply evidence-backed judgments and the application derives the final category. Missing required information remains uncertain; explicit required conflicts and unrelated functions take precedence. Exact quotations validate provenance, although they cannot establish that a model's interpretation is correct. The Decisions conversion is versioned under `broad-v3`; earlier review findings about its unchanged identity and aggregate-experience score citation have been addressed in current source.

**Security and privacy have substantive controls.** Owner authentication uses Argon2 and hashed random session tokens. State-changing authenticated requests require origin and CSRF checks. CVs stay outside static assets; fetched descriptions render as text; document parsing runs in a resource-limited subprocess; search does not receive candidate data. Secret mounts are scoped by service, runtime images are mostly digest-pinned, and fetchers have neither database credentials nor CV storage. These are meaningful controls, subject to the deployment and request-boundary findings below.

**Delivery and recovery are conservatively designed.** Digest dates are unique, scheduling uses local calendar time with explicit DST handling, and ambiguous sends are not automatically repeated. Server acceptance is distinguished from device receipt. Backup scripts encrypt streams without plaintext staging, stop writers for consistency, restore into new volumes, and reject unsafe archive entries. Preserve these guarantees while fixing compatibility and accounting integration.

### Architecture costs and tradeoffs

The main complexity is in custom operational control: application operations plus queue jobs, two accounting stores, dynamic host firewall rules, and scripts with host-specific assumptions. The **second billing ledger and firewall lifecycle coupling are the weakest boundaries**, because neither participates fully in deployment, recovery, or owner-facing configuration.

The shared ntfy server is a reasonable owner-specific adaptation. It also makes installation dependent on an existing external network/service, changes the trust surface of `edge` and `worker`, and makes ntfy backup/version/availability an external responsibility. A dedicated publisher token narrows application permissions; the external server's lifecycle and restore contract still need explicit acceptance. Do not silently replace or reconfigure the owner's shared service.

The single-profile advisory lock simplifies cross-component invariants and is reasonable here. It also serializes substantial finalization work; large source inventories and digest snapshots can delay other transactions. Job search computes a full-text expression at query time, and snapshot selection loads every eligible digest row. These are performance risks to measure with a representative inventory, not sufficient evidence to demand a new database or caching layer.

The original advice in [ADVISE.md](ADVISE.md) remains sound: freeze optional feature expansion and demonstrate the useful monitoring loop. New-results indicators and further visual polish should not displace correctness, representative source coverage, and recovery work.

## High-severity findings

### ER-01 — Production inference is coupled to a development-only, lifetime-limited file ledger

**Evidence:** [provider.py](backend/app/ai/provider.py), `infer` at line 721 and admission at line 790; `dispatch_decisions` at line 492; [run_ledger.py](backend/app/ai/run_ledger.py), constants at line 17 and `_locked`; [config.py](backend/app/config.py), line 26; [compose.yaml](compose.yaml); [backend.Dockerfile](deploy/backend.Dockerfile).

Every live inference constructs `RunLedger`, despite its development-only purpose. Its default relative path resolves under `/app/.data`, while the shipped backend container runs as UID 10001 with a read-only root filesystem. Compose supplies neither a writable ledger mount nor its path setting. Enabling `INTEGRATION_MODE=live` therefore cannot use this default inference path successfully once admission reaches the ledger. The database reservation is created first; an uncaught ledger filesystem error can later become an unresolved billing reservation even though no inference POST was sent.

Simply mounting the file does not complete the fix: the ledger imposes **60 requests / US$1 for the entire lifetime**, independently of the portal's daily limits. It is not included in the normal backup volume set, and the API's manual reconciliation does not update it (ER-05). Thus validation accounting has become an undocumented production dependency.

**Required correction:** separate explicitly enabled validation accounting from normal operating budgets. Preserve the existing cumulative validation allowance and history; do not reset or bypass it. If the ledger remains required for any deployment mode, give it explicit durable ownership, shared access, backup/reconciliation rules, and clear UI status. Handle failed pre-dispatch admission without inventing an ambiguous external charge.

**Closure:** with mocked transport and the actual read-only container settings, prove ordinary configured inference, restart persistence, admission-failure accounting, and the distinction between daily production limits and the preserved validation ceiling. No paid request is needed to test these cases.

### ER-02 — The chosen Decisions matching path is not available through normal setup

**Evidence:** [contracts.py](backend/app/ai/contracts.py), `TaskConfig.protocol` at line 22; [ai.tsx](frontend/src/features/settings/ai.tsx), `TaskForm`; generated [openapi.json](frontend/src/lib/openapi.json) and [api-types.ts](frontend/src/lib/api-types.ts); [config.py](backend/app/config.py), line 29; [provider.py](backend/app/ai/provider.py), line 467; [compose.yaml](compose.yaml).

The backend requires an explicit `protocol="decisions"` revision for the selected Jev model. The Settings form exposes no protocol control or model-to-protocol resolution. Both generated TaskConfig schemas omit the field. On a fresh configuration, entering that model ID leaves the backend's default `chat` protocol in effect. The live harness succeeds by inserting the correct configuration directly into the database; that does not prove owner setup works.

Even a correctly provisioned revision encounters `decisions_live_enabled=False`: the shipped Compose environment never maps that setting. Putting an otherwise unused variable in the Compose interpolation file does not pass it into a container. This is a functional deployment gap, not a recommendation to turn off a billing safeguard casually.

There is a related configuration honesty issue: the Decisions dispatch does not honor all fields exposed by the generic form, including the selected provider list and chat generation controls. Unsupported restrictions must be rejected or explained rather than silently accepted.

**Required correction:** regenerate the API contract, make supported protocol selection unambiguous in owner setup, expose the approved runtime activation path, and validate protocol-specific settings. Preserve the documented owner decision and billing limits.

**Closure:** a fresh-database browser journey configures the intended model through Settings, saves the correct protocol, and exercises the appropriate mocked endpoint using the same effective configuration as Compose. Also test changing a preconfigured Decisions task back to a chat model.

### ER-03 — Fetch isolation can outlive the rules that made it safe

**Evidence:** [jobfinder-fetch-control.service](deploy/jobfinder-fetch-control.service), lines 4 and 11; [fetch-control-rules.sh](deploy/fetch-control-rules.sh), `install` and `verify` at line 170; [http.py](backend/app/fetcher/http.py), `fetch`; [compose.yaml](compose.yaml), restart policy and fetcher environment; [check-deployment.py](scripts/check-deployment.py), acceptance-file check.

The fetcher trusts a static boolean. Its rules reference current container IPs, while the oneshot systemd unit only orders itself after Docker, remains active, and has no dependency on application-container readiness or recreation. A reboot can start automatically restarting containers before rule installation; a later recreation can invalidate the stored IPs without rerunning the unit. Failure or rollback does not revoke the enabled fetcher flag. The current disabled default limits immediate exposure, but this is a defect in the eventual enabled lifecycle.

Additionally, `verify` checks rule counts and whether source IP text occurs anywhere in `DOCKER-USER`. It does not prove the marked rules have the expected targets, ordering, interfaces, destination/port, or current INPUT addresses. For example, changing a marked DROP target to ACCEPT preserves the checks. The acceptance file is accepted on `status == "accepted"` without binding it to the current image/rule/configuration identity.

**Required correction:** define one start/recreate/stop sequence that keeps fetching disabled until the exact current policy is verified, and disables it on policy loss. Verify complete managed rule semantics and precedence, and bind acceptance to the relevant deployment identity. Avoid a window in which stale rules are removed while live fetching remains enabled.

**Closure:** controlled target-host tests for reboot, changed container IPs, Docker restart, failed install, stopped unit, and modified rule targets/order. Demonstrate both allowed fetching and forbidden live-listener access throughout the relevant transitions. Static counts alone are insufficient.

### ER-04 — Deployment preflight silently expands into privileged runtime work

**Evidence:** [check-deployment.py](scripts/check-deployment.py), `verify_firewall_rules` at line 17, especially the non-root branch at line 27.

With fetching enabled, the advertised configuration checker can run `alpine:latest` on host networking, add `NET_ADMIN`, disable startup NNP, mount the Docker socket and repository read-write, and run `apk add` before invoking verification. `--pull never` prevents an image pull; it does not prevent those package downloads. The helper's effective access is far broader than a read-only firewall check.

This violates the tool's stated no-start behavior and makes a seemingly harmless preflight depend on network package installation and broad host access. It also reads the checkout's deployment env-file inside the helper rather than explicitly propagating the file passed to preflight. No such branch was executed during this review.

**Required correction:** keep static preflight genuinely static. Make host verification a separate explicit operation with already-installed, narrowly scoped tooling and the same resolved deployment parameters. If privileged access is unavailable, report that verification is outstanding. Do not install tooling inside an implicitly privileged helper.

**Closure:** mock subprocess tests assert that configuration inspection never creates containers, installs packages, or mounts the Docker socket, and that alternate deployment parameter files reach any separately requested verifier.

## Medium-severity findings

### ER-05 — Manual billing verification does not release the file-ledger hold

**Evidence:** [api/ai.py](backend/app/api/ai.py), `verify_cost` at line 215; contrast [ai/tasks.py](backend/app/ai/tasks.py), `reconcile_call`, which calls `RunLedger.settle`.

After an ambiguous live request, the owner can verify its actual charge through the UI. That endpoint updates PostgreSQL to `owner_reconciled` but never settles the cumulative ledger. The UI can show the uncertainty resolved while further requests still fail admission. This is particularly restrictive for Decisions calls, which reserve the entire remaining allowance. Automatic reconciliation is no longer available once the row is no longer `unknown`.

**Correction and closure:** use one idempotent reconciliation operation for both owner and provider verification, with recoverable ordering across stores. A mocked ambiguous-call → owner-verification → next-admission test must prove that the hold is released exactly once while actual spend and attempt counts are preserved. Include interruption between the two stores.

### ER-06 — Existing backups are incompatible after the ntfy topology change

**Evidence:** [recovery.py](scripts/recovery.py), `VOLUMES` at line 12 and exact payload-set check at line 121; [backup.py](scripts/backup.py), format declaration at line 216; preceding revision `243ae96^:scripts/recovery.py`.

The shared-ntfy change removed `ntfy_state.tar.gpg` from the expected payloads but retained manifest format `1`. A backup created by the preceding implementation therefore fails the new exact set comparison before restoration. This is a recovery compatibility regression, although it does not establish that the owner has an affected real backup or that its data is lost.

**Correction and closure:** version the archive manifest and support the previous format explicitly. Verify all original payloads, then restore only the appropriate application state into isolated volumes; do not automatically overwrite the shared ntfy service. Test a previous-format fixture and a current-format fixture with current tools, and document the separate shared-service recovery responsibility.

### ER-07 — Generic-source expiry evidence cannot retire a stored job

**Evidence:** [generic_inventory.py](backend/app/collection/generic_inventory.py), lines 35 and 42; [selectors.py](backend/app/collection/selectors.py), closed-card handling at line 116; [inventory.py](backend/app/collection/inventory.py), `update_availability` and line 255.

A generic vacancy initially collected as open becomes `active`. If a later page gives an expired `validThrough`, the parser discards that candidate and adds an issue. A configured closed marker is likewise discarded. Non-authoritative sources do not reconcile omissions, and there is no separate explicit-closure update. The stored association stays available indefinitely. A stale generic association can also prevent closure of a job shared with an ATS source that has reliably closed it.

Preserving jobs during missing/failed collection is correct; preserving an **active assertion despite explicit expiry evidence** is not the same behavior. The API offers `unknown`, but reviewed automatic paths do not transition jobs into that state.

**Correction and closure:** carry identity-bound verified closure/expiry observations separately from open postings, and define availability aging when current evidence is unavailable. Test open → explicit expired/closed, partial-run non-closure, and mixed-source availability. Keep historical jobs browsable.

### ER-08 — Lease exhaustion does not finalize the associated business state

**Evidence:** [worker.py](backend/app/tasks/worker.py), `dispatch` at line 30; [inventory.py](backend/app/collection/inventory.py), `begin_run` at line 44; [operations.py](backend/app/services/operations.py), normal exception finalization; [api/operations.py](backend/app/api/operations.py), retry behavior.

After a third interrupted attempt, dispatcher recovery marks only the operation failed. It does not invoke the collection/profile failure transitions, clear all lifecycle metadata, or finish the collection run. `begin_run` finds the still-collecting epoch and returns its already-failed page operation until the epoch expires. “Check now” can therefore join dead work rather than recover collection. Profile documents/drafts can retain queued/processing state while their operation has failed. Discovery has a special interrupted-step check; collection lacks the equivalent.

Separately, the generic retry endpoint requeues a terminal `source_collect` without reopening its failed run; `prepare_page` then rejects the run as no longer collecting. A new company check can recover that ordinary failure, but the generic retry contract is inconsistent.

**Correction and closure:** centralize terminal recovery transitions per operation kind, preserve lease fencing, and either restart/reopen a valid epoch deliberately or return an actionable new-check response. Inject worker loss through the final attempt and verify operation, source/run, draft, UI status, and subsequent manual/scheduled recovery together.

### ER-09 — The CV upload limit is enforced too late to bound request resources

**Evidence:** [profiles.py](backend/app/api/profiles.py), `upload_document` at line 156; [Caddyfile](deploy/Caddyfile), API proxy handler; installed FastAPI `routing.py` parses `request.form()` before solving dependencies, and installed Starlette `formparsers.py` spools file parts without applying its non-file part limit.

The handler reads at most 10 MiB plus one byte, but FastAPI has already consumed the multipart file before the handler and its authentication dependency run. There is no edge request-body limit. Thus a reachable unauthenticated client can cause oversized files to spool, consuming the API's bounded `/tmp` and request-processing resources before receiving rejection.

**Fresh reproduction:** an isolated in-memory FastAPI route using the installed framework parsed **11,534,336 file bytes before returning 401**. File spooling was replaced with BytesIO; no actual disk fill, application request, or credential was involved. The framework emitted a Starlette TestClient/httpx deprecation warning; the reproduction otherwise exited 0.

**Correction and closure:** enforce a total streaming request-size limit before multipart parsing, with multipart overhead allowance, at the edge and/or ASGI boundary. Test oversized authenticated and unauthenticated requests, including absent/chunked Content-Length, while showing that valid supported CVs still upload.

### ER-10 — The ntfy check proves neither successful publishing nor absence of writes

**Evidence:** [check-ntfy.py](scripts/check-ntfy.py), denied POST checks and final OPTIONS check. The recorded server version is 2.28.0; its [upstream routing and OPTIONS implementation](https://github.com/binwiederhier/ntfy/blob/v2.28.0/server/server.go#L649) handles OPTIONS outside topic-write authorization and returns CORS headers.

The checker treats OPTIONS 200 as proof of publish authorization. A valid credential with no permitted topic can satisfy all the denial checks and that OPTIONS check. A fresh mocked run with publishing and reading always denied returned exit 0 and printed the publisher-verification claim.

The checker also attempts two POSTs while claiming no test notification was sent. Those requests are expected to fail, but if the ACL is wrong, publishing is precisely their possible effect. An empty body does not make a publish request read-only.

**Correction and closure:** separate read-only ACL/configuration inspection from an explicitly requested synthetic publish/receipt test. A deny-all credential must not pass a publish-permission claim. Label denial probes as potential writes and use a dedicated test topic/server for mutation-capable checks. Existing recorded denials remain useful negative evidence; they do not replace positive publish or phone-delivery acceptance.

### ER-11 — Gates E and F provide narrower evidence than the records claim

**Evidence:** [evaluate-semantic-cases.py](scripts/evaluate-semantic-cases.py), `run_m5` at line 262, `run_x3`, and `historical_passes`; [verify-phase-f-journey.py](scripts/verify-phase-f-journey.py), direct profile insertion at line 281, direct `process_operation` invocation, and usage inspection; [VALIDATION.md](VALIDATION.md), 2026-10-10 Gates E/F entry.

Specific gaps are observable:

- M5 prints PASSED without asserting salary status, comparability, or exclusion behavior. AST inspection confirmed zero assertions in that case.
- X3 compares the literal string `evil.invalid` with link IDs, rather than checking the resolved selected URL. The extraction validator provides separate protection; that assertion does not prove the claimed result.
- Resumed semantic runs insert hardcoded prior-pass results without binding them to the current code, prompts, configurations, or run artifacts.
- Phase F seeds model revisions and inventory, calls profile analysis directly, inserts an approved revision directly, and invokes the operation handler synchronously. It bypasses upload/parsing/review activation, actual queue dispatch, source fetching, and scheduling.
- The “portal” checks are TestClient API calls. Usage validation only checks HTTP 200 and prints a nonexistent top-level `daily_usd`; it does not compare the file ledger with database/UI totals.

These runs are valuable live adapter/service integration evidence. They do not demonstrate the complete owner journey, browser behavior, or accounting agreement described in the records.

**Correction and closure:** narrow the existing claims; add outcome assertions and artifact/version binding. On the intended host, execute the missing owner-facing and queued paths. Keep paid tests explicitly opt-in: these two runners currently enter live execution directly, unlike the dedicated gated launcher. Do not rerun them casually to complete this review.

### ER-12 — JavaScript-rendered collection remains unimplemented

**Evidence:** [SOURCES.md](SOURCES.md), Generic browser adapter and fetch contract; [IMPLEMENTATION.md](IMPLEMENTATION.md), delivery step 4; [runner.py](backend/app/collection/runner.py), adapter allowlist; [backend/pyproject.toml](backend/pyproject.toml); [backend.Dockerfile](deploy/backend.Dockerfile).

The agreed implementation includes bounded Playwright rendering/load-more for JavaScript career pages. The backend has no Playwright dependency or rendering handler; the image provides HTTP-only fetching; collection accepts only the three ATS adapters and `generic_http`. Frontend Playwright tests do not implement source rendering. Current progress explicitly calls the rendering engine unfinished.

This is missing implementation, not just an unrun deployment test. HTTP extraction cannot recover vacancies absent from the returned HTML. The effect on particular target employers requires actual inspection; no employer-specific unsupported claim is made here.

**Correction and closure:** either complete the existing bounded, isolated browser contract and its acceptance matrix, or obtain an explicit product-scope change to HTTP/ATS-only support and update all claims. Before calling the original scope complete, demonstrate a representative source that genuinely requires rendering without weakening isolation.

### ER-13 — Model-save copy hides automatic paid reassessment

**Evidence:** [ai.tsx](frontend/src/features/settings/ai.tsx), line 372; [api/ai.py](backend/app/api/ai.py), `update_ai` at line 71; [services/matching.py](backend/app/services/matching.py), `expand` and `enqueue`.

The portal says saving a model choice does not make a paid request. Saving `job_matching` creates a new configuration and a `profile_reassess` operation; the worker can then assess existing open inventory in live mode. This happens independently of the separate validation-cost checkbox, and dispatch does not require `validation_state="validated"`. Saving an unchanged configuration also creates a new identity and can reassess the inventory.

Automatic reassessment is consistent with the design; the misleading part is the user-facing cost promise and lack of an explanation of the resulting batch.

**Correction and closure:** clearly state which settings changes queue reassessment and may incur cost, avoid needless identical revisions, and keep synthetic validation distinct. An end-to-end mocked test should verify the queue effect and the notice shown before save; do not imply the validation checkbox controls ordinary matching costs.

### ER-14 — Operational history has no implemented 30-day retention

**Evidence:** [DATA_MODEL.md](DATA_MODEL.md), Retention; [services/retention.py](backend/app/services/retention.py); [worker.py](backend/app/tasks/worker.py), maintenance and `delete_jobs="successful"`; operation/collection/discovery models.

Maintenance expires approved document originals, page extractions, and source snapshots. It does not prune operation intents, collection runs/pages/observations, discovery history, or expired sessions. Queue cleanup covers successful Procrastinate jobs, not the application history. A daily monitor therefore accumulates operational rows indefinitely despite the documented 30-day policy.

This also means old run history and growing backup size need explicit capacity treatment. Conversely, deleting operations naively would break deduplication and foreign-key references, so a blanket age-based delete is not safe.

**Correction and closure:** define which receipts and referenced records must survive, then implement bounded cleanup/archive of eligible operational data. Preserve active leases, unresolved billing, notification ambiguity, assessment provenance, and necessary idempotency receipts. Test retention against both active/referenced and expired unreferenced rows.

### ER-15 — Healthy HTTP does not expose stalled monitoring, and unexpected worker errors lose diagnostics

**Evidence:** [main.py](backend/app/main.py), `/health/live`, `/health/ready`, and `/status`; [services/operations.py](backend/app/services/operations.py), broad exception conversion; [settings/page.tsx](frontend/src/features/settings/page.tsx); [DEPLOYMENT.md](DEPLOYMENT.md), operational visibility requirements.

`/status` reports configured integration mode, profile presence, and a fixed phase. It does not expose queue age, control-tick freshness, worker heartbeat, fetch enablement, or independent search/notification readiness. The Settings label “Live integrations” is derived only from AI mode. API liveness stays healthy with dead workers or disabled collection, while the readiness route is limited to database schema.

Unexpected handler exceptions become generic `processing_failed` messages without a structured diagnostic log or error classification. The queue handler can return normally after storing that failure, leaving neither useful worker traceback nor specific operator evidence. Database errors are similarly redacted without logging. Redaction is appropriate; losing the safe diagnostic cause is unnecessary.

**Correction and closure:** expose minimal durable freshness/backlog/dependency status and record sanitized operation IDs, exception classes, and failure locations. Keep private payloads out of logs. Kill a worker or inject a handler failure in an isolated test and show that the owner can distinguish a stalled monitor from a working but empty source.

### ER-16 — Lever traversal has no 200-page stop

**Evidence:** [ats.py](backend/app/collection/ats.py), `decode_page` at line 118 and continuation at line 154; [inventory.py](backend/app/collection/inventory.py), generic frontier bound at line 151 and continuation at line 230; [SOURCES.md](SOURCES.md), 200-page run limit.

The 200-page bound is applied only to the generic URL frontier. A full Lever page always creates another offset. If a source repeats a full page or ignores `skip`, duplicate observations add `unstable_pagination`, but traversal continues. It can repeatedly fetch and persist page operations until the 24-hour epoch limit, instead of stopping at the promised cap. The limit of 20,000 rows in `decode_page` applies to one response, not the accumulated Lever traversal.

**Correction and closure:** enforce a shared page/row budget and stop on provably non-progressing pagination while retaining partial coverage and avoiding omission closure. Use a mocked source that repeats 100 rows indefinitely; assert bounded requests, terminal partial status, and preserved inventory.

### ER-17 — Validation errors are not consistently actionable or accessible

**Evidence:** [lib/api.ts](frontend/src/lib/api.ts), error schema and `ApiError`; [main.py](backend/app/main.py), validation-error envelope; [profile/editor.tsx](frontend/src/features/profile/editor.tsx), selected domains at line 739 and criterion description at line 772; [settings/ai.tsx](frontend/src/features/settings/ai.tsx), server-error display.

The backend returns `field_errors`, but the client keeps only status/code/message. For backend-only validation, such as an unsupported model identifier, the UI can display “Check the highlighted fields” without having the field information needed to highlight them. Several profile controls render an error paragraph but lack `aria-invalid`/`aria-describedby`, unlike the summary and desired-role fields. There is no consistent linked summary for all invalid fields.

**Correction and closure:** retain typed field errors, map them to form fields, and associate each inline error with its control. Focus a linked error summary after failed submission where multiple fields can fail. Verify keyboard and screen-reader behavior for model validation, focus domains, and dynamic criteria. The local `ui-ux-pro-max` error-summary guidance supports these specific changes; this review does not claim a completed WCAG audit.

## Low-severity finding

### ER-18 — Documentation and static-check entry points no longer describe one clear current state

**Evidence:** [PLAN.md](PLAN.md), execution status; [DECISIONS.md](DECISIONS.md), newer deployment update versus older model/input statements; [DEPLOYMENT_API_VALIDATION.md](DEPLOYMENT_API_VALIDATION.md), top budget summary versus final gate table; [DEPLOYMENT.md](DEPLOYMENT.md), older bundled-ntfy/check descriptions and backup volume count; [PROGRESS.md](PROGRESS.md); [VALIDATION.md](VALIDATION.md).

New dated checkpoints coexist with unqualified older “current” sections. Examples include two versus 46 recorded inference attempts in the API-validation companion, already-created scripts described as absent, an old disposable ntfy checker description after it was replaced with a live-host checker, and a five-volume backup description after the format changed. These inconsistencies make safe continuation and release assessment harder. Historical evidence should be retained, but clearly scoped to its date and commit.

Static lint is also not currently reproducible as one clean project gate. The root invocation with the project config reported 17 errors; the backend-directory invocation reported 75, predominantly import grouping, plus the same overlong recovery-test line. This directory sensitivity should be resolved through explicit source/import configuration and a canonical command. It is not evidence of 75 runtime defects.

**Correction and closure:** maintain one concise current release/acceptance table with links to dated history, synchronize the relevant runbooks, and define stable lint/type/schema checks. A generated-API drift check would have caught ER-02. Keep exact test scope and commit identity with every completion claim.

## Acceptance and development-evidence assessment

The development record contains useful evidence, including a reported 340-test backend pass, earlier component and 11-browser-journey results, live model-schema/judgment checks, isolated restore exercises, and recent direct-IP TLS/health checks. They establish progress in their respective environments and revisions. They were not rerun here, and their scopes should not be merged into a single production-acceptance claim.

| Area | What the repository supports | What remains unproven or incomplete |
| --- | --- | --- |
| Authentication/profile editing | Implemented revision checks, private sessions, parser bounds, and historical synthetic browser coverage | Current built-edge upload/review/activation journey and upload boundary correction |
| ATS and generic collection | Substantive adapters, snapshot caching, durable traversal, identity/coverage guards | Representative real-employer coverage and long-running lifecycle behavior; rendering absent |
| Live AI | Reported live schema and selected synthetic judgment success | Normal portal/Compose setup, production accounting, complete semantic assertions, representative useful matching |
| Fetch containment | Reported positive proxy/private-target/directional-listener checks | Lifecycle persistence, exact-rule verification, enabled current-deployment binding, browser boundary |
| DNS rebinding | Recorded denial of a hostname resolving to loopback | A controlled public-to-private resolution change is not established by a static loopback-resolving hostname alone |
| Portal | Historical Vite/component/browser journeys and current accessible structural patterns | Fresh built-Caddy browser acceptance for current code, protocol setup, field-error behavior, assistive-technology testing |
| Notifications | Strong ledger/ambiguity design, historical isolated transport checks, recent negative ACL checks | Genuine positive publish authorization through application worker and scheduled owner-device receipt |
| Recovery | Encrypted streaming and reported isolated synthetic restore | Previous-format compatibility, current full application restore, external ntfy responsibility, installed timer and recovery-time targets |
| Private ingress | Recent recorded direct-IP TLS and HTTP 200 results | Those results do not establish tailnet ACLs, outside-LAN denial, trusted client certificates, or all private-ingress acceptance |

The `localtest.me` result should be described as a useful **private-address DNS resolution rejection**. It does not by itself demonstrate resistance to a changing DNS answer between validation and connection. The proxy's connection-time checks are an appropriate design; the broader acceptance claim needs a controlled test.

Test coverage is broad around invariants, but integration seams are underrepresented: frontend-generated contracts versus backend models; file versus database accounting; prior versus current backup formats; environment flags versus real container filesystems; and terminal operation state versus domain state. Add focused tests at those seams rather than pursuing a larger test count as an end in itself.

## Fresh review checks and limits

All checks below were performed without project runtime mutations. Pure reproductions used synthetic in-memory objects. Python bytecode/cache output was disabled, and Ruff ran with `--no-cache`.

| Check | Result | Interpretation |
| --- | --- | --- |
| Git baseline/status/history inspection | Baseline `e6b1fa9`; clean at intake | Findings apply to that source state, not uninspected private deployment overrides |
| Python AST parsing across application, migrations, tests, and scripts | 138 files; zero syntax errors; exit 0 | Syntax only; not execution/type/database validation |
| `bash -n deploy/fetch-control-rules.sh scripts/test-fetch-control-harness.sh` | Exit 0 | Shell syntax only; no firewall commands executed |
| Mocked `check-ntfy.py` with all topic read/write permission denied | Checker returned 0 and claimed publisher verified | Reproduces ER-10 false positive; both attempted POSTs were intercepted in memory |
| Prior/current backup volume-set comparison | Previous format includes `ntfy_state`; current exact set rejects it | Reproduces manifest incompatibility without reading any backup or secret |
| Semantic M5 AST inspection | Zero assertions | Confirms the salary acceptance outcome is not checked by that case |
| Generated TaskConfig schema inspection | `protocol` absent from both input and output schemas | Confirms API contract drift |
| Isolated installed-framework upload/auth test | 11 MiB parsed before HTTP 401; exit 0 | Confirms ordering with memory-only spooling; not a deployed denial-of-service test |
| `backend/.venv/bin/ruff check --no-cache --config backend/pyproject.toml backend scripts --output-format concise` from repo root | Exit 1; 16 I001 and one E501 | Fresh static findings, no autofix |
| `.venv/bin/ruff check --no-cache --config pyproject.toml app tests ../scripts --output-format concise` from `backend` | Exit 1; 74 I001 and one E501 | Confirms directory-sensitive import classification; no autofix |
| Local UX guidance search: `error summary validation`, domain `ux` | Relevant focusable-summary, announcement, and associated-inline-error guidance | Used for ER-17, not a substitute for browser/assistive-technology validation |

The normal shell sandbox initially failed before command execution with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` (exit 1). Read-only inspection then used the permitted expanded execution path. No dependency operation was attempted or retried.

No application test suite, browser launch, build, container start, deployment preflight, live validation runner, real ntfy checker, backup/restore, or firewall operation was executed. No secrets, real CVs, or private runtime ledger contents were read. Dependency vulnerability status and complete third-party supply-chain integrity were not assessed; lockfiles and image pinning alone do not establish those properties. The public ntfy source was consulted only to verify the specific OPTIONS behavior in ER-10.

## Recommended remediation and sign-off order

1. **Repair the normal live setup path:** address ER-01/02/05 together without resetting the validation budget; synchronize schema/UI/protocol controls and account for unsupported protocol settings.
2. **Close isolation lifecycle and tooling boundaries:** address ER-03/04 before enabled fetching, including current-identity verification and restart/recreation tests.
3. **Repair data/recovery behavior:** address backup compatibility, vacancy expiry, lease exhaustion, upload limits, and bounded pagination. Add regression tests at the failure boundary each finding identifies.
4. **Make validation claims precise:** correct ER-10/11 and separate static inspection, service integration, browser acceptance, and device receipt. Preserve dated successful evidence with its actual limits.
5. **Resolve rendering scope and prove the benefit on the intended host:** reviewed profile → representative real collection → broad matching → built portal → scheduled digest received by the owner. Include a difficult source and visible coverage failures.
6. **Finish operation and recovery acceptance:** safe retention, actionable worker/dependency status, nightly backup execution, and an isolated restored-application journey. Then update the current release record and rerun the affected static/type/schema/browser checks.

The existing system is a substantial foundation. Release confidence now depends on fixing these concrete seams and demonstrating the supported owner workflow with the deployed configuration, rather than adding more architecture or optional features.
