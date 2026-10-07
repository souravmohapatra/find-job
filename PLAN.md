# Delivery plan

Updated: 2026-10-07. Technical decisions are now authorized and documented. Implementation is active; current evidence and outstanding gates are recorded below.

## Intended outcome

Upload and review one domain-agnostic CV profile, choose preferences and companies, collect vacancies on schedule, assess suitability with explanations, and receive local ntfy alerts. All collected company jobs remain available. Operate on Ubuntu Server via Docker Compose, LAN and tailnet only.

## Planning completed

- Product intent and boundaries: [CONTEXT.md](CONTEXT.md).
- Selected architecture and stack: [ARCHITECTURE.md](ARCHITECTURE.md), [IMPLEMENTATION.md](IMPLEMENTATION.md).
- Persistence and API contracts: [DATA_MODEL.md](DATA_MODEL.md), [API.md](API.md).
- Collection and assessment: [SOURCES.md](SOURCES.md), [MATCHING.md](MATCHING.md).
- Interface and local operations: [UI_UX.md](UI_UX.md), [DEPLOYMENT.md](DEPLOYMENT.md).
- Decision rationale and alternatives: [DECISIONS.md](DECISIONS.md), [RESEARCH.md](RESEARCH.md).

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

- Milestone 1: dependencies, owner authentication, app shell, real PostgreSQL migrations and initial durable workers validated locally. Docker image builds, integrated private ingress and production network boundaries remain pending; the development database uses the explicit host-network exception.
- Milestone 2: local document parsing, reviewed profile revisions, preferences and diversification implemented with mock analysis; a real API/database/worker browser journey passes. Task-model Settings and provider integration now have mocked transport and real local browser validation. Profile data-management controls are implemented and locally validated. Explicit profile/draft conflict recovery is implemented and validated locally. Billing-recovery UI is implemented and browser-validated locally. Richer synthetic analysis fixtures and live provider acceptance remain pending.
- Milestone 3: ATS decoders, durable inventory/scheduling, company/source APIs and all-jobs portal have synthetic and local database/browser validation. Actual isolated source collection, conditional snapshots and remaining coverage/count UI still need integration.
- Milestone 4: bounded HTTP fetcher/RPC implemented with synthetic tests; proxy ACLs have network-none container validation. Generic JSON-LD parsing has synthetic validation. Persistent official-URL discovery and ATS source verification are implemented and under integration validation. Brave/name-only search, persistent budgets, explicit candidate confirmation and portal discovery history are implemented with mocked-provider/local validation. Employer-verified generic JSON-LD collection, persistent bounded page traversal and non-authoritative coverage are implemented and locally validated. Unstructured/AI extraction, browser fallback, declarative selectors, conditional snapshots, named-employer coverage and complete network isolation remain pending.
- Milestone 5: broad matching contracts/policy, versioned persistence, bounded reassessment worker and current/stale shortlist API are implemented with synthetic local validation. Explanation UI, feedback, manual reassessment, representative mocked browser journeys and live model acceptance remain pending. Mock/live results have separate identities.
- Milestones 6–7: pending, including notifications, representative model/source checks and deployment-environment network validation. No release completion is claimed.
