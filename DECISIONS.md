# Decision register

## R1 solution without Docker migration — 2026-10-10

Owner assigned removal of the Snap Docker NNP startup blocker and explicitly excluded Docker migration. Selected and tested the smallest project-local workaround: keep Docker startup NNP enabled by default, allow explicit `DOCKER_NO_NEW_PRIVILEGES=false` for this Snap host, and always apply `setpriv --no-new-privs` inside the already-attached container profile before service/helper execution. Health checks use the same wrapper. Preflight rejects missing payload/health wrappers, inconsistent startup options and invalid setting values.

This preserves NNP on application processes and their descendants, along with existing AppArmor/seccomp/user/capability/filesystem/network restrictions. The trusted initial launcher/init and arbitrary administrative Docker exec sessions are outside that inheritance; wrap required administrative commands explicitly. No daemon migration, restart, confinement change or global security relaxation is part of this solution. Activation and rollback are in DEPLOYMENT.md. R1 validation does not close DNS/fetch-isolation or release gates.

## Current deployment validation direction — 2026-10-09

The owner assigned continuation on the deployment host under [FINISH_DEVELOPMENT_AND_VALIDATE.md](FINISH_DEVELOPMENT_AND_VALIDATE.md) and [DEPLOYMENT_API_VALIDATION.md](DEPLOYMENT_API_VALIDATION.md). The former development-network local live validation remains canceled.

Active models: `openai/gpt-6-luna` for profile analysis and job extraction, and TypeSafe Jev (`typesafe/jev-1.13`) for job matching, through OpenRouter. Jev task-boundary adapter is implemented per the Phase D contract: fail-closed typed normalization, 5-anchor relevance scoring mapped by `round_half_up(25 * native_score)` to 0..100, dynamic `domain_status` enforcing `focus` mode, dynamic `important_unknowns`, bounded exact evidence candidates (<= 500 chars), separate score sufficiency, non-coerced connection choices (supported/unsupported/unknown), strict candidate-supported score evidence provenance, and per-criterion comparability checks; versioned under `broad-v3` and `matching-decisions-v3`. 340 backend tests pass.

Budget reconciliation: On 2026-10-09, the owner confirmed that the **US$1 cap is an advisory validation budget**, not a hard provider-side ceiling, and the provider key's $5 monthly limit serves as an outer backstop. If any single call or batch exceeds US$1, halt and consult the owner. The durable ledger (`.data/live_run_ledger.json`) enforces admissions. Recorded activity on the deployment host: **2 inference attempts, US$0.000020042 known spend, US$0 held spend**, and 1 key-metadata GET. Remaining allowance under the advisory cap: 58 attempts, US$0.999979958.

Unfinished gates remain explicitly open: Phase D generative profile/extraction schemas, prompt/semantic evaluation (Phase E), fetch isolation on real containers (section 9), end-to-end monitoring journey (section 11), ntfy device delivery (section 12), and deployed recovery (section 13).
## Historical deployment continuation update — 2026-10-08 (preset direction superseded)

The owner will move continuation to the deployment environment, use a local LLM as the development agent, supply an OpenRouter API key privately, and create `@preset/job-finder` for application LLM testing. This supersedes the earlier statement that the initial test model reference is entirely unset. Keep profile_analysis, job_extraction and job_matching independently configurable; all may initially use the same preset. The development agent's local model does not replace OpenRouter in the application. Underlying preset models are selected by the owner in OpenRouter.

The current application rejects preset identifiers and assumes concrete models in capability/response checks. Supporting the preset is remaining implementation work, not a verified capability. A finite live-test budget, private key and preset availability are still prerequisites. The original guide proposed USD 1 / 20 attempts; that proposal was superseded by the approved cumulative USD 1 / 60-request cap above. That guide records the ordered host, implementation and acceptance steps; no live request or deployment change occurred while preparing it.

Updated: 2026-10-07. User requirements and delegated implementation decisions are distinguished below. Selected defaults can be revised with evidence; they are not claims of user approval of every detail or of runtime validation.

## Confirmed user requirements

| ID | Decision |
| --- | --- |
| D01 | Personal project; no employer-internal systems or trackers. |
| D02 | Docker Compose on Ubuntu Server, LAN and local tailnet access, no public access. Supersedes “hosting details later.” |
| D03 | Web portal and locally hosted ntfy. |
| D04 | One active CV-derived profile, editable by the user. |
| D05 | Domain-agnostic analysis and logic; consulting/finance/entertainment are example context only. |
| D06 | Optional diversification beyond existing professional domains. |
| D07 | Persist company requests; daily/custom checks, including companies without careers pages. |
| D08 | AI assesses collected jobs against saved profile/preferences. |
| D09 | All collected company jobs remain available regardless of matching. |
| D10 | Polished, minimalist UX. |
| D11 | Decide and document implementation details now. Supersedes the earlier high-level-only constraint; implementation itself is not requested yet. |
| D12 | Local Git autonomy while preserving user work; no remote publication authorized. |
| D13 | OpenRouter API for all LLM work, independent models per task; exact models decided later. No local LLM. |
| D14 | Broad manual-review shortlist at roughly 30% relevance; exclude unrelated primary functions, do not optimize strict matching. |
| D15 | Configurable daily summary, default 19:00 in the owner's timezone; daily/twice-daily checks are independent. |
| D16 | Netflix, Spotify, Amazon, Revolut, Airwallex and similar employers are development-only examples, not product presets. |

## Selected implementation decisions

| ID | Choice and rationale | Detail |
| --- | --- | --- |
| T01 | Build focused app using libraries; avoid inheriting broader platform scope. | IMPLEMENTATION.md, RESEARCH.md |
| T02 | React/TypeScript/Vite, Tailwind/shadcn; FastAPI/Pydantic Python backend. | IMPLEMENTATION.md, UI_UX.md |
| T03 | PostgreSQL, SQLAlchemy/Alembic, Procrastinate; durable jobs without Redis. | IMPLEMENTATION.md, DATA_MODEL.md |
| T04 | Immutable profile/job revisions and versioned assessments; collection independent of suitability. | DATA_MODEL.md |
| T05 | OpenRouter integration with versioned per-task model mappings, capability validation and bounded spend. Supersedes the initial local-inference proposal under D13; no model IDs selected. | MATCHING.md |
| T06 | Broad 30/100 heuristic inclusion with primary-function boundary; both match/possible entries shortlisted. Supersedes stricter fit rules and precision targets. | MATCHING.md |
| T07 | Domain focus/expand/open; open default with explicit setup review. | MATCHING.md |
| T08 | ATS APIs first, generic HTTP/browser fallback, Brave company discovery; no logged-in scraping. | SOURCES.md |
| T09 | One owner account, private sessions, isolated fetching, mounted secret files. | DEPLOYMENT.md |
| T10 | Caddy LAN HTTPS and host Tailscale Serve; no wildcard public publishing or Funnel. | DEPLOYMENT.md |
| T11 | Daily 19:00 local digest includes both shortlist categories; separately label baselines/reassessments, handle late assessments and DST. Supersedes the 15-minute, matches-only default. | DEPLOYMENT.md, MATCHING.md |
| T12 | Jobs/Companies/Profile plus secondary Settings; all-jobs and explanation views. | UI_UX.md |
| T13 | PDF text/DOCX/TXT, explicit review, no OCR in v1; replacement CV uses a merge draft. | MATCHING.md |
| T14 | Conservative identity/closure rules; partial runs never close missing jobs. | DATA_MODEL.md, SOURCES.md |
| T15 | Local notifications by default; external iOS wake-up/Web Push disabled. | DEPLOYMENT.md |
| T16 | Nightly private backups with restore drill; 30-day operational retention, seven-day fetch diagnostics. | DATA_MODEL.md, DEPLOYMENT.md |

## Alternatives considered

- Full platform fork: more existing functionality, but broader scope and licence obligations; no fork selected.
- SQLite plus an in-process scheduler: smaller service count, but weaker fit for multiple durable workers and concurrent state transitions.
- Celery/Redis: viable, but another stateful service is unnecessary for this scale.
- Local inference: superseded by the user's explicit OpenRouter requirement. No local model infrastructure is planned.
- General browsing agent: flexible, but controlled adapters and bounded extraction are easier to validate.
- Multi-profile or application tracker: useful future scope, unnecessary for the first requested journey.

## Inputs and evidence still needed

Exact per-task OpenRouter model IDs remain intentionally deferred. Actual deployment addresses, tailnet policy, owner credentials, OpenRouter key, Brave key if automatic discovery is wanted, and backup location remain to be supplied. Pin compatible dependencies during implementation and record task configuration/model provenance for each call. Model quality and performance, generic-site coverage, client certificate trust and notification behaviour require execution evidence. They have not been tested.

Future scope includes additional ATS adapters, OCR, automatic company suggestions and multiple profiles. These are extensions, not blockers for the selected initial design.

## Development environment exception — 2026-10-07

User-approved: keep PostgreSQL and the existing backend test URL, using an opt-in Linux host-network test-container override with PostgreSQL restricted to 127.0.0.1:55439. This avoids the blocked development Docker bridge without changing VPN/host routes or application architecture. Verified host SQL access and the current backend test suite. Normal Compose topology remains the deployment design and requires validation on the intended Ubuntu server before release; this exception does not authorize host-network fetchers or production services.
