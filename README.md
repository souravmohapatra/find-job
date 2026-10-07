# AI-assisted job finder

A locally hosted application that learns a candidate's profile from a CV, watches selected companies, builds a broad shortlist from editable preferences, and sends a configurable daily local ntfy summary at 19:00 by default. All collected company vacancies remain available for manual browsing.

Status: product and implementation design documented. Application code and deployment are not implemented.

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
