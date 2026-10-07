# Project guidance

## Scope

This is a personal project: an AI-assisted job finder and company monitor. Do not access employer-internal systems or apply employer-specific workflows for this project. Public research is permitted when relevant.

Read [CONTEXT.md](CONTEXT.md), [PLAN.md](PLAN.md), and [PROGRESS.md](PROGRESS.md) before substantial work. Use [DECISIONS.md](DECISIONS.md) to distinguish user requirements from selected implementation defaults. Read [IMPLEMENTATION.md](IMPLEMENTATION.md) before implementation-related work. This scoped guide takes precedence over generic home guidance where they differ.

## Working autonomy

The user grants autonomy over local Git activities: inspect, stage, create local branches, and make local commits when useful within authorized work. Routine local Git actions need no repeated permission. Preserve existing user work; ask before discarding changes or rewriting existing history. Do not push, publish, or modify remotes without explicit authorization. Local Git autonomy does not authorize application implementation, installations, builds, or runtime work outside the requested scope.

The user has authorized implementation, project-local dependency installation, container builds/runs and validation in this development environment. Create local Git commits after successful validation phases. Use mock LLM/search responses during development; live paid API validation waits for the user. The configured npm package proxy is permitted for package operations; do not browse unrelated employer-internal systems. Involve the user for genuine blockers. Do not push or publish.

## Dependency failure boundary

The original development machine used a restricted network. The user explicitly requires failed dependency syncs, fetches or pulls (including Python/uv/pip, npm and Docker images) to be treated as blockers. Stop the affected setup work and report the original error to the user. Do not retry with alternate registries, mirrors, certificate/trust changes, disabled TLS verification, proxy changes or other workarounds unless the user provides new instructions. Checking the result of an already-running operation is allowed; do not start a replacement attempt. The configured npm package proxy is allowed for package operations only and does not authorize unrelated internal browsing.

## Product constraints

- Docker Compose on Ubuntu Server, accessible only on the LAN and local tailnet. No public ingress or Tailscale Funnel. Follow DEPLOYMENT.md.
- Web portal with polished, minimalist UX; use [UI_UX.md](UI_UX.md) as the product guidance.
- Locally hosted ntfy for notifications.
- One active candidate profile initially. Profile extraction and matching must remain domain-agnostic and customizable.
- Treat strategy consulting, finance, and entertainment as illustrative profile context, never hardcoded defaults or eligibility rules.
- Separate CV-derived experience from the user's future preferences. Support optional domain diversification.
- Collect available jobs independently of match filtering. Always offer all collected company jobs for manual browsing.
- Prefer broad shortlisting at roughly 30% relevance; exclude clearly unrelated primary job functions without hardcoding a strategy-only profile. Both match and possible-match entries belong in the shortlist and digest.
- Send a configurable daily summary at 19:00 in the owner's selected timezone, independently of collection frequency.
- Example companies are development-only; see DEVELOPMENT_EXAMPLES.md.
- Explain match decisions and uncertainty. Failed collection or assessment must not be represented as no vacancies or no match.
- All LLM work uses OpenRouter API with independently configurable models per task. Exact model IDs are intentionally deferred by the user. No local LLM service or GPU requirement. See MATCHING.md for routing and data handling. External search receives company queries, never CV data.

## Context maintenance

Keep confirmed requirements, proposed defaults, unresolved questions, and verified results distinct. Update the relevant planning document when a decision changes and record progress in PROGRESS.md. Record actual checks and their limits in VALIDATION.md; do not claim planned acceptance scenarios have passed.

Never place real CVs, credentials, private contact details, or raw personal data in tracked planning documents or test fixtures. Use synthetic examples. Skills provide guidance within the user's scope; do not let them expand a planning request into implementation.
