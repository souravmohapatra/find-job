# Advice on project direction and engineering scope

Date: 2026-10-09. Based on the assessment recorded in [REVIEW.md](REVIEW.md), saved in local commit `0aeb034`, and the subsequent discussion with the owner. This document records advice, not a new implementation assignment or a change to confirmed requirements. See [CONTEXT.md](CONTEXT.md) for product scope and [DECISIONS.md](DECISIONS.md) for requirements versus selected defaults.

## Judgment

The project is still on track in product scope, but execution has drifted toward overengineering before proving usefulness.

There is substantial working implementation and credible local validation. The application still serves the intended purpose: learn a reviewed candidate profile, monitor selected companies, show all collected vacancies, build a broad shortlist and send a daily digest. There is no evidence here of a wholesale diversion into an unrelated product.

The concern is the order and breadth of work. Extensive recovery controls, provider accounting, extraction configuration and interface refinement were built before proving that real companies yield useful shortlists and that a scheduled digest reaches the owner. The project has accumulated a meaningful maintenance burden while its main benefit remains unverified.

Keep the existing application, freeze expansion and focus on acceptance. A rewrite would create another diversion and could lose useful correctness guarantees.

## Complexity that serves the requirements

This product needs more than a scraping script. The following mechanisms have concrete purposes:

| Mechanism | Why it is justified |
| --- | --- |
| Inventory independent of matching | The owner must be able to browse every collected job, including rejected or unassessed roles. |
| Reviewed, versioned profiles and assessments | User corrections must survive, and work using old preferences must not appear current. |
| Explicit collection and assessment failures | A broken source or model must not be displayed as no vacancies or no match. |
| Durable scheduling and bounded retries | Monitoring must survive restarts without losing work or repeating requests indefinitely. |
| Fetch isolation and private access | External websites must not reach private services, credentials or candidate data. LAN/tailnet-only deployment is a requirement. |
| Spending controls and unknown-cost handling | External inference needs bounded admission and truthful accounting, especially after ambiguous failures. |
| Timezone-aware digests | The daily summary is tied to the owner's local time, independently of collection frequency. |
| Basic backups and a restore drill | The owner must be able to recover saved profiles, monitored companies and inventory. |

PostgreSQL with a database-backed queue is a defensible choice because it avoids another broker. The Compose service count alone does not establish overengineering: several services share an image and two are one-shot setup jobs. The important question is the ongoing operating burden, not the raw number of containers.

The present DNS/isolation work is necessary. It should be finished with demonstrated boundaries before arbitrary fetching is enabled. It should not be dropped simply to make the architecture smaller.

## Where the work became premature

| Area | Judgment | Practical response |
| --- | --- | --- |
| Recovery and configuration interfaces | Some advanced workflows were polished before real usage established how often they would matter. Conflict protection and truthful errors remain necessary. | Keep implemented controls; defer additional recovery/configuration refinement unless an acceptance failure requires it. |
| Collection breadth | ATS adapters, JSON-LD, AI extraction, selectors, previews and browser fallback collectively approach a general collection platform. Broad source support is relevant, but implementing many paths before representative live evidence increases uncertainty. | Prove a small representative company set, including a difficult source, before expanding adapters or extraction features. Retain visible coverage limits. |
| Provider accounting | Basic limits and unresolved-cost protection are necessary. Detailed recovery machinery and UI became substantial before model usefulness was established. | Preserve existing protections; finish the required model tests before adding accounting features. |
| Operation lifecycle | Application intents, leases and recovery coexist with the queue's lifecycle. This has transactional reasons but creates maintenance work. | Do not add more lifecycle states without a concrete failure. Review overlap only after identifying which guarantees must survive. |
| UI polish and optional features | Responsive, accessible core journeys serve the requirement. Further convenience features do not answer whether monitoring works. | Freeze optional polish and indicators until the deployed core journey passes. |

Premature does not mean useless, unauthorized or safe to delete. Much of this breadth was selected in the implementation plan. The problem is investing in it before the evidence that should guide its final shape.

## What the attempts reveal

Mock-first development was appropriate under the original network constraints and deferred model selection. It produced useful evidence about transactions, concurrency, stale-result protection, failures and interface behavior. Authored mock decisions do not establish that a real model will produce useful judgments.

Moving to the intended host, checking public-registry portability, using normal bridge networking and completing a disposable restore drill were meaningful steps toward the earlier review's recommendations. The small live Luna/Jev probes established transport progress. They did not establish acceptance of the real profile/extraction schemas, useful matching, privacy enforcement beyond observable request acceptance, or the complete monitoring journey.

The firewall attempts illustrate a process weakness. Advisory checks caught missing protocol selection, per-network address handling, host INPUT coverage, idempotency and listener-liveness issues. Those corrections were useful, but basic offline checks and well-defined baselines should precede privileged runs.

The DNS failure was observed after rules without a pre-rule DNS baseline. The subsequent resolver exception therefore addressed an assumed cause. At the review baseline, its rule counts also caused four of six mocked installer tests to fail. The lesson is to establish the failing layer first, then make one small change and rerun the relevant check. Later uncommitted edits may change those findings; this advice does not claim to have revalidated them.

The same distinction applies to Jev. A successful typed probe is progress, but the reviewed adapter still hardcoded unknown domain fit and important uncertainty. Matching acceptance needs evidence-supported judgments and the original deterministic shortlist policy, not merely a response that parses.

## Recommended course

1. **Freeze expansion.** Defer new capabilities, frameworks, adapters and optional polish. Fix defects needed for the agreed core journey and its release gates.
2. **Finish the current isolation blocker.** Pass the mocked installer checks, establish separate external-name/internal-service DNS baselines and demonstrate any restricted resolver path. Complete the actual isolation matrix before enabling arbitrary URLs.
3. **Complete the model acceptance work.** Test the actual profile/extraction schemas and finish Jev's domain, uncertainty, evidence and relevance conversion. Use a small authored semantic set; preserve broad shortlisting and both shortlist categories.
4. **Prove the complete benefit.** Run reviewed profile → representative real collection → useful broad matching → portal → scheduled ntfy digest received on the owner's device. Include a difficult source and report incomplete coverage honestly.
5. **Close operational gates.** Verify private deployed access, nightly backup execution and deployed-application recovery. Do not treat an isolated helper test as deployed acceptance.
6. **Choose subsequent work from evidence.** Expand coverage or refine workflows where real failures and owner feedback show a need. Keep already-implemented features without making their further refinement prerequisites.

Before another paid batch, reconcile the conflicting budget guidance and carry forward the recorded two inference attempts and known spend against the durable ledger. This advice does not authorize further requests, reset the allowance or change the ceiling.

Success should be judged by demonstrable outcomes: real monitored jobs remain browsable, the broad shortlist is useful and explained, failures stay visible, the scheduled digest arrives and the owner can operate and recover the app. More code, test counts and completed documents are supporting evidence, not substitutes for these outcomes.

## Limits

This is an engineering judgment based on the recorded progress and sampled code reviewed earlier. It is not a fresh full audit, a recommendation to weaken security or a declaration that all existing complexity is unnecessary. No exact deletion estimate is justified without tracing the guarantees and callers involved.

No application tests, live calls, host changes or implementation fixes were performed for this advice document. The main remaining risk is that deployment and real-world usefulness are still unverified.
