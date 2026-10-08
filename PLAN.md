# Delivery plan

Updated: 2026-10-08. Technical decisions are now authorized and documented. Implementation is active; current evidence and outstanding gates are recorded below.

## Intended outcome

Upload and review one domain-agnostic CV profile, choose preferences and companies, collect vacancies on schedule, assess suitability with explanations, and receive local ntfy alerts. All collected company jobs remain available. Operate on Ubuntu Server via Docker Compose, LAN and tailnet only.

## Planning completed

- Product intent and boundaries: [CONTEXT.md](CONTEXT.md).
- Selected architecture and stack: [ARCHITECTURE.md](ARCHITECTURE.md), [IMPLEMENTATION.md](IMPLEMENTATION.md).
- Persistence and API contracts: [DATA_MODEL.md](DATA_MODEL.md), [API.md](API.md).
- Collection and assessment: [SOURCES.md](SOURCES.md), [MATCHING.md](MATCHING.md).
- Interface and local operations: [UI_UX.md](UI_UX.md), [DEPLOYMENT.md](DEPLOYMENT.md).
- Decision rationale and alternatives: [DECISIONS.md](DECISIONS.md), [RESEARCH.md](RESEARCH.md).

## Next acceptance priority — advisory review response, 2026-10-08

The advisory review in REVIEW.md identifies sequencing as the main concern: extensive local checks do not yet prove useful real-world monitoring. Prioritize the following within the existing scope; this is not a reduction of requirements or a claim that deployment gates have passed.

1. Finish the basic backup/restore path already underway, including an isolated synthetic restore drill and clear operating instructions.
2. Defer new capabilities and optional polish, including the new-results indicator and further advanced configuration/recovery UI work, until the core journey has real evidence. Fix defects needed for that journey.
3. On the intended Ubuntu host, validate deployment/network isolation and prove reviewed profile → real company collection → broad matching → portal → scheduled ntfy delivery to the owner's device.
4. Start with a small representative company set, including one difficult source, then expand to the agreed development examples. Report coverage gaps explicitly.
5. Choose subsequent improvements from observed failures and owner feedback. Keep implemented features; do not start a rewrite or simplify queue recovery without first establishing which guarantees must survive.

The host/network work, off-network dependency portability and authorized live provider checks remain prerequisites. Exact OpenRouter models and paid validation remain deferred until the user supplies choices/authorization. A blocked acceptance gate should be surfaced rather than indefinitely replaced with peripheral feature work. All original milestone and release obligations below remain tracked.

## Implementation milestones

| Order | Deliverable | Completion evidence required |
| --- | --- | --- |
| 1 | Locked stack, migrations, owner auth, UI shell, Compose boundaries | Clean bootstrap, login/session checks, private ingress and dependency readiness |
| 2 | CV upload/review, one versioned profile, editable preferences | Synthetic CV journey, concurrent edit protection, diversification controls |
| 3 | ATS collection and scheduled company inventory | Greenhouse/Lever/Ashby fixtures, pagination, all-jobs view, restart/idempotency checks |
| 4 | Company discovery and generic collection | Five named development employers plus category examples, missing-careers-page fixture, browser isolation and honest coverage gaps; see DEVELOPMENT_EXAMPLES.md |
| 5 | Broad AI shortlisting and explanations | Small function-boundary/transferability examples, unknown handling, stale-result protection and profile reanalysis; no precision tuning campaign |
| 6 | ntfy delivery and local operations | Daily 19:00 timezone-aware digest of both shortlist categories, late assessment/DST/ambiguous-send handling, private access and restore drill |
| 7 | Integrated release candidate | Browser/accessibility journeys, representative opt-in live checks, documented quality/performance limits |

Milestones are a plan; the user has now authorized implementation and its builds/tests. [VALIDATION.md](VALIDATION.md) defines the gates. Dependencies are intentional: first establish reliable inventory, then evaluate matching, then alert on its results.

## Decisions deliberately bounded

A focused application will reuse libraries rather than a whole platform. Keep the initial product to one owner/profile and selected-company monitoring. No embeddings/vector database, second AI judge, auto-apply, public SaaS, or broad application tracker is required.

Selected OpenRouter model accuracy, source-specific generic extraction, dependency compatibility, API cost/latency, and deployment resource needs must be measured during implementation. These are verification obligations, not reasons to leave the architecture undecided. Actual host names, addresses, credentials and backup destination are installation inputs. Exact OpenRouter models are intentionally deferred by the user; task configuration and mocking permit implementation before selection, while live model acceptance waits for it.

## Execution status

- Milestone 1: dependencies, owner authentication, app shell, real PostgreSQL migrations and initial durable workers validated locally. All ten Compose services, edge/ntfy image definitions and private ingress configuration now exist; template boundary checks, Caddy runtime-base configuration and isolated non-root ntfy ACL checks pass. Full application image builds, integrated private ingress and production network boundaries remain pending; the development database uses the explicit host-network exception.
- Milestone 2: local document parsing, reviewed profile revisions, preferences and diversification implemented with mock analysis; a real API/database/worker browser journey passes. Task-model Settings and provider integration now have mocked transport and real local browser validation. Profile data-management controls are implemented and locally validated. Explicit profile/draft conflict recovery is implemented and validated locally. Billing-recovery UI is implemented and browser-validated locally. Richer synthetic analysis fixtures and live provider acceptance remain pending.
- Milestone 3: ATS decoders, durable inventory/scheduling, company/source APIs and all-jobs portal have synthetic and local database/browser validation. Company coverage/count summaries have local API/browser validation, including pause/cooldown dates and preserved All jobs navigation. Conditional HTTP snapshots now have mocked transport/database validation for ATS and generic collection. The company-detail job list, company-scoped filters, active/unknown defaults and return navigation now have local API/component/browser validation. Actual isolated source collection remains pending.
- Milestone 4: bounded HTTP fetcher/RPC implemented with synthetic tests; proxy ACLs have network-none container validation. Generic JSON-LD parsing has synthetic validation. Persistent official-URL discovery and ATS source verification are implemented and under integration validation. Brave/name-only search, persistent budgets, explicit candidate confirmation and portal discovery history are implemented with mocked-provider/local validation. Employer-verified generic JSON-LD collection, persistent bounded page traversal and non-authoritative coverage are implemented and locally validated. Unstructured AI extraction now has a persisted fetch-to-AI handoff, evidence/employer/open-status guards and explicit cached retries, validated with synthetic local fixtures. Conditional snapshots are integrated with local lease/expiry/304 validation. Declarative website selectors and cached-page preview APIs now have synthetic/local database validation, including non-authoritative empty-page safety. The advanced portal rule editor, cached preview, conflict draft handling and automatic-mode restoration now have local component/browser validation. Browser fallback, named-employer coverage and complete network isolation remain pending.
- Milestone 5: broad matching contracts/policy, versioned persistence, bounded reassessment worker and current/stale shortlist API are implemented with synthetic local validation. Explanation UI, feedback and manual reassessment are implemented; feedback save/reload has real API/browser validation. A mocked assessment-worker-to-shortlist browser journey now passes, including profile preference changes and both shortlist categories. Bounded periodic reconciliation now covers policy upgrades/rollbacks and missing current intents without silently retrying failed calls. Live model acceptance remains pending. Mock/live results have separate identities.
- Milestone 6: timezone-aware daily calendar calculations have synthetic validation. Persistent eligibility events, daily digest snapshots, settings/history APIs and control-tick integration are implemented and locally validated with synthetic fixtures. Delivery attempts/recovery and bounded ntfy transport now have mocked local validation, with full backend and focused recovery/cooldown regression checks passing. Explicit resend/test actions and notification Settings/history UI are implemented and locally validated, including the real API/worker browser journey. An isolated non-root local ntfy server now passes publish-only token, reader-only access, anonymous denial and cached-receipt checks. Basic encrypted backup and isolated restore scripts now pass a disposable full-data restore drill. Application-worker-to-ntfy Compose delivery, deployment networking, nightly scheduling/retention and deployed-application recovery remain pending.
- Milestone 7: route splitting reduces initial JavaScript to 137.34 KB gzip and removes the oversized-chunk warning; all 11 local browser journeys pass, including failed-import recovery. Representative model/source checks, new-results indicators, backup/restore and deployment-environment network validation remain pending. No release completion is claimed.
