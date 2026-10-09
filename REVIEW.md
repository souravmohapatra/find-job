# Progress, approach and attempts review

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
