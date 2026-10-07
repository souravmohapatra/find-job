# AI-assisted job finder

A locally hosted application that learns a candidate's profile from a CV, watches selected companies, builds a broad shortlist from editable preferences, and sends a configurable daily local ntfy summary at 19:00 by default. All collected company vacancies remain available for manual browsing.

Status: implementation in progress. Authentication and the CV upload/review/preferences workflow have local PostgreSQL/worker/browser validation with mock inference. Company monitoring, live AI configuration, matching and notifications are still in progress. Ordinary Compose networking still needs validation on the deployment host. This is not yet a usable job finder or a verified deployment.

Selected foundation: React/TypeScript/Vite, FastAPI/Python, PostgreSQL with Procrastinate workers, OpenRouter with per-task model selection, and ntfy. Docker Compose on Ubuntu Server; LAN and tailnet access only.

## Planning and implementation map

| Document | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Workspace rules and authorized scope |
| [CONTEXT.md](CONTEXT.md) | Intent and user requirements |
| [PLAN.md](PLAN.md) | Delivery milestones |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Logical and runtime architecture |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | Stack, code structure, background execution |
| [DATA_MODEL.md](DATA_MODEL.md) | Tables, identity, history and invariants |
| [API.md](API.md) | API routes and response contracts |
| [MATCHING.md](MATCHING.md) | CV analysis, diversification, assessment policy |
| [SOURCES.md](SOURCES.md) | Discovery, adapters and safe collection |
| [DEVELOPMENT_EXAMPLES.md](DEVELOPMENT_EXAMPLES.md) | Development-only employers and broad-shortlist examples |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Compose services, private networking and operations |
| [UI_UX.md](UI_UX.md) | Interface and accessibility requirements |
| [DECISIONS.md](DECISIONS.md) | User requirements and selected defaults |
| [RESEARCH.md](RESEARCH.md) | Reuse alternatives and evidence limits |
| [VALIDATION.md](VALIDATION.md) | Planned acceptance gates and actual check evidence |
| [PROGRESS.md](PROGRESS.md) | Current state and continuation notes |

Start with CONTEXT.md, IMPLEMENTATION.md and PLAN.md. Decisions are documented; installation-specific values and execution evidence remain outstanding.

## Current development checks

With frontend dependencies installed through the configured npm proxy:

```sh
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run test:e2e
```

Browser tests use the installed Google Chrome channel and start a local-only Vite server. They mock API responses; they do not test real backend authentication. `npm --prefix frontend run dev` starts the frontend on 127.0.0.1:5173 and proxies API requests to 127.0.0.1:8000. It requires a working backend for interactive sign-in; no mock account or credentials are shipped in the app.

Dependency failures must be reported without registry, certificate or network workarounds; see AGENTS.md. See PROGRESS.md for current evidence and remaining work before application startup.

## Backend tests on this development machine

With the locked backend dependencies installed and the PostgreSQL test image already cached:

```sh
python3 scripts/init-dev.py
docker compose -f compose.test.yaml -f compose.test.host.yaml up -d --wait --pull never db
python3 scripts/test-backend.py -q
```

The override is Linux development-only. PostgreSQL listens on 127.0.0.1:55439; it does not use a port mapping. If switching from the regular bridge test setup, stop that test service first to release the same port. The test database is disposable (tmpfs); container recreation resets it. Secrets are generated locally only when missing, and the user's .env is preserved. Never point the test suite at production data. Omit the host override when validating standard Docker bridge networking on the deployment server.

## Profile workflow validation

`npm --prefix frontend run test:integration` starts a real loopback API and worker plus Vite, using a dedicated disposable `jobfinder_test_browser` database on the running test PostgreSQL instance. It seeds only a synthetic owner/CV and tears down its server processes afterwards. This command never uses the real CV supplied for local parsing checks. `npm --prefix frontend run generate:api` regenerates frontend types from FastAPI's OpenAPI schema.

For an optional real local parsing check, run `backend/.venv/bin/python scripts/check-cv.py /path/to/cv.pdf`. It prints aggregate metrics only, retains no extracted text, and makes no AI request. Put additional real examples in ignored `private-fixtures/`; use synthetic inputs in committed tests.
