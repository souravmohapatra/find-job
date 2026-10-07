# Implementation design

Design baseline: 2026-10-07. The user authorized technical decisions and documentation. This is an implementable plan, not an implemented or tested application.

## Foundation and stack

Build a focused application in this repository using established libraries. Do not fork an existing job platform. Our central model is a reviewed candidate profile plus an unfiltered company vacancy inventory; adopting a broader product would bring workflows we do not need. This is an architectural judgment from documentation review, not a measured comparison of running products. See [RESEARCH.md](RESEARCH.md).

| Area | Selection | Reason |
| --- | --- | --- |
| Web client | React 19, TypeScript, Vite | Responsive application with no need for server rendering or public search indexing. |
| UI | Tailwind CSS 4, shadcn/ui with Radix primitives, Lucide icons | Locally owned components with consistent accessible interactions. |
| Client data/forms | TanStack Query, React Router, React Hook Form, Zod | Server-state caching, URL-backed navigation, structured editable forms. |
| API | Python 3.12, FastAPI, Pydantic 2, Uvicorn | Shared validation contracts and a useful document/collection ecosystem. |
| Persistence | PostgreSQL 17, SQLAlchemy 2, psycopg 3, Alembic | Transactions, JSONB snapshots, relational integrity, and migrations. |
| Background work | Procrastinate using PostgreSQL | Durable jobs, locks, retries, and periodic tasks without another broker. |
| Fetching | HTTPX, Beautiful Soup/lxml, Playwright Chromium | Prefer HTTP and structured content; render only when necessary. |
| CV text | pypdf, python-docx, plain UTF-8 text | Support text PDFs, DOCX, and TXT without external document services. |
| Inference | OpenRouter API over HTTPX; task-specific model settings | One integration, independently selected models for CV analysis, job extraction and matching. Exact models deferred. |
| Discovery | Brave Search API plus bounded website traversal | Company-name discovery with a documented search API. |
| Delivery | ntfy HTTP publishing | Direct integration with the local server. |
| Edge | Caddy; host-managed Tailscale Serve | LAN HTTPS and tailnet-only access. |
| Fetch isolation | Squid egress proxy | Prevent fetched pages from reaching private services. |
| Tooling | uv; Node 22 build environment with npm lockfile; Ruff, mypy, ESLint, Prettier | Reproducible installs and straightforward checks. |
| Tests | pytest, Vitest/Testing Library, Playwright, axe-core | Backend invariants, frontend behaviour, real browser journeys. |

These are selected version families, not an assertion that every latest release works together. Resolve and commit exact compatible package versions, browser version, and container digests during the first implementation milestone. Never deploy floating `latest` images. No Redis, vector database, agent framework, Kubernetes, local model server or GPU is needed. The application stays private while making outbound requests to OpenRouter and configured search providers.

[FastAPI documents its validation/OpenAPI support](https://fastapi.tiangolo.com/features/); [shadcn documents Vite integration](https://ui.shadcn.com/docs/installation/vite). [Procrastinate provides PostgreSQL-backed tasks and scheduling](https://procrastinate.readthedocs.io/en/stable/index.html).

## Source tree to create during implementation

```text
backend/
  pyproject.toml, uv.lock
  app/
    api/             # routes, auth, request/response contracts
    domain/          # matching policy, entities, state transitions
    services/        # transactional use cases
    db/              # ORM models and repositories
    tasks/           # scheduling, reconciliation, background handlers
    sources/         # source discovery and ATS/parser adapters
    ai/              # provider protocol, schemas, versioned prompts
    documents/       # CV validation and text extraction
    notifications/   # ntfy events and delivery ledger
    fetcher/         # isolated fetch/render service
  migrations/
  tests/             # unit, integration, synthetic fixtures
frontend/
  src/
    app/             # routing, providers, layout
    features/        # jobs, companies, profile, settings
    components/ui/   # owned shadcn components
    lib/             # generated API types and query helpers
  tests/
deploy/              # image definitions, Caddy/Squid/ntfy templates
scripts/             # bootstrap, checks, backup, restore
compose.yaml
compose.test.yaml
```

Root Markdown files remain the planning/context layer. Runtime data and secrets live outside Git; development fixtures use synthetic identities. Do not create empty implementation scaffolding as part of this design task.

## Worker and scheduling design

Use named queues `control`, `fetch`, `ai`, and `notify`. Two worker services share the backend image: a general worker consumes control/fetch/notify (four concurrent tasks initially), and an AI worker consumes ai (two concurrent requests initially, subject to provider rate limits and spend budgets). Queue isolation prevents slow inference from delaying collection or notifications.

A Procrastinate periodic control task runs every minute, queries persisted `next_due_at` values, and creates one durable operation intent for each due source. Intervals default to 24 hours, offer daily (24h) and twice-daily (12h) presets, are editable from 1 hour to 30 days, and use UTC durations with small jitter. Store the user's IANA timezone separately. Daily digest scheduling uses a local wall-clock time (default 19:00), not an interval timer; see DEPLOYMENT.md. Prevent overlapping checks of the same source. A manual check joins an existing pending operation and respects source backoff.

After downtime, schedule one catch-up per source; do not replay every missed interval. Set the next regular due time to catch-up start plus interval/jitter, not an already missed historical slot. Retries do not advance the regular due time. Unresolved company discovery also receives a daily check, subject to search budgets. Each control tick also reconciles up to 100 missing current assessment intents, handling policy upgrades/rollbacks and mode changes without automatically retrying failed or blocked inference.

Persist operation intents in the same transaction as the business change that requires work. A periodic dispatcher forwards pending intents to Procrastinate. Since queue and ORM connections may differ, do not assume atomicity across them: enqueue may repeat after a crash. Every handler claims its stable operation ID, checks completion, and writes results idempotently. Single-intent claims wait for a dispatcher-held row lock (bounded by a 10-second PostgreSQL lock timeout); they must not use SKIP LOCKED and acknowledge an existing locked intent as missing. Bulk dispatch scans can still skip locked rows. Queue locks reduce duplication; database constraints and operation state enforce correctness. Reconcile stale operations and Procrastinate stalled workers every five minutes. [Supported queue mechanisms](https://procrastinate.readthedocs.io/en/stable/howto/advanced.html).

Default transient retries: three attempts, exponential delay with jitter, obeying Retry-After. Invalid inputs, blocked sites, and schema errors must not retry indefinitely. Rate limits use per-origin persisted cooldowns, shared across collectors. Long-running work has bounded timeouts and visible progress; terminal failures stay inspectable and manually retryable. Notification ambiguity has its own policy in DEPLOYMENT.md.

## API and state discipline

Use `/api/v1`, generated OpenAPI client types, server-side filtering/pagination, and JSON error envelopes. See [API.md](API.md). Changes to reviewed profile data create immutable revisions. Assessment completion only becomes current when its profile, job, policy and task-model configuration versions still match. New revisions make older work historical rather than overwriting newer decisions.

The browser polls operation status every two seconds during active user work and backs off to 30 seconds for visible background status. Pause polling when hidden. No WebSocket service is needed initially. All jobs are database records independent of assessment state.

## Delivery order

1. Bootstrap locked dependencies, migration flow, authentication, empty UI shell, Compose networking, and health checks.
2. CV ingestion/review, immutable profile revisions, preferences, diversification, and OpenRouter task-model Settings; use synthetic CVs and mocked inference until real models are chosen.
3. Company requests, Greenhouse/Lever/Ashby collection, durable scheduling, inventory and all-jobs UI.
4. Discovery, generic HTML/JSON-LD extraction, browser fallback, and fetch isolation. Include a company without a careers page.
5. Structured assessment, versioned policy, explanation UI, feedback, and reassessment.
6. ntfy summaries/digests, delivery state, restart recovery, backups, and LAN/tailnet deployment checks.
7. Execute quality evaluation and accessibility/security/recovery gates in VALIDATION.md before describing the app as usable.

Each milestone should deliver a reviewable working slice. Authentication, profile workflow and task-model Settings have local API/database/worker/browser validation. Normal Compose deployment acceptance and the remaining inventory/matching/notification milestones are pending. See PROGRESS.md for current evidence.
