# API contract

REST JSON under `/api/v1`, served from the same origin as the web client. FastAPI/Pydantic owns the contracts; generate TypeScript types from OpenAPI. Browser credentials use secure owner sessions, not localStorage bearer tokens. All routes except login and minimal liveness require authentication.

## Initial routes

| Method and path | Behaviour |
| --- | --- |
| POST /auth/login; POST /auth/logout; GET /auth/me | Owner session creation/revocation and session state. |
| GET /profile | Current reviewed profile, revision and draft status. |
| GET /profile/documents | Owner-only paginated document metadata (20 per page); no original filename or extracted text. |
| PATCH /profile/documents/{id}/retention | Change original-file retention for an available document. |
| POST /profile/documents | Multipart upload; validates limits and returns document/operation IDs with 202. |
| GET /profile/drafts/{id}; PATCH /profile/drafts/{id} | Review/edit extracted draft; no change to active profile. |
| POST /profile/drafts/{id}/reconcile | Explicit owner-reviewed merge; If-Match checks the current profile and draft_version checks the draft. Saves a reconciled draft without activation. |
| POST /profile/drafts/{id}/activate | Activate reviewed facts and preferences using expected base revision; queues reassessment. |
| PATCH /profile | Update reviewed facts/preferences with If-Match revision; creates a new revision. |
| GET /profile/documents/{id}/download | Authenticated original-file download if retained; never a public static URL. |
| DELETE /profile/documents/{id} | Purge original/raw document artifacts without silently deleting reviewed facts. |
| POST /profile/purge | Explicit owner-confirmed purge of CVs, profile history, and dependent assessments. |
| GET /companies; POST /companies | List watches; create name/URL watch and discovery operation. |
| GET /companies/{id}; PATCH /companies/{id} | Company state, interval, pause/resume, and identity correction. |
| POST /companies/{id}/discover; POST /companies/{id}/check | Durable on-demand operation, joining pending work when present. |
| GET /companies/{id}/sources; POST /companies/{id}/sources | Inspect discovery results and add/confirm source URLs. |
| PATCH /sources/{id} | Confirm/disable source, edit interval and supported declarative options. |
| GET /sources/{id}/runs | Bounded collection history and coverage/errors. |
| GET /jobs | Cursor-paginated inventory with view/company/availability/text filters. |
| GET /jobs/{id} | Job detail, provenance, current assessment and version history summary. |
| POST /jobs/{id}/reassess | Assess current revisions; idempotent, returns operation ID. |
| PUT /jobs/{id}/feedback | Relevant/not relevant feedback plus optional reason. |
| GET /operations/{id} | queued/running/blocked/succeeded/failed/cancelled, progress and safe error. Block reasons distinguish missing configuration, credits/budget and provider capability failures. |
| GET /settings; PATCH /settings | Non-secret timezone, notification and budget preferences. |
| POST /settings/notifications/test | Explicit test message to configured local ntfy. |
| GET /settings/ai; PATCH /settings/ai | Per-task model IDs, routing/limits and active configuration revisions; model IDs may remain unset until selected. |
| GET /settings/ai/models | Server-side OpenRouter catalog/capability view, cached; no secret exposed. |
| POST /settings/ai/validate | Explicit configuration check using minimal synthetic input; may incur API cost, never uses a CV. |
| PATCH /settings/ai/limits | Versioned AI daily call/spend limits; If-Match uses limits_revision. |
| POST /settings/ai/usage/{id}/reconcile | Queue generation-metadata billing reconciliation when an unresolved request has a generation ID. |
| POST /settings/ai/usage/{id}/verify | Record an explicitly confirmed owner-verified cost for an unresolved request; no inference retry. |
| GET /settings/ai/usage | Per-task usage, estimated/reported cost, reservations and paused states. |
| GET /notifications | Sent/failed/ambiguous delivery history. |
| GET /health/live; GET /health/ready; GET /status | Liveness, DB/migration readiness, authenticated dependency/backlog status. |

Profile purge uses a dedicated confirmation in the UI. Removing a company initially means pause/archive via PATCH, preserving job history; irreversible company deletion is not a necessary v1 action.

## Query and response semantics

`GET /jobs?company_id=...&view=all` omits suitability predicates and includes unassessed and failed assessments. Default view `recommended` (labelled Shortlist) includes current match and possible_match using the broad inclusion policy. `availability=all` includes closed/unknown jobs; filters and counts remain explicit. Results use a stable `(first_seen_at,id)` cursor for both recommended and all jobs; default page size 30, maximum 100. Company job counts are computed under clearly labelled scope.

Long-running actions return 202 with `{operation_id, resource_id, status_url}`. Clients do not wait for scraping or inference in an HTTP request. Mutating operation endpoints accept Idempotency-Key; its owner/route scope and request hash prevent accidental reuse with different input. Database uniqueness still protects scheduled tasks.

Errors use `{code, message, field_errors, request_id}`. Use 409 for revision conflicts, 413 for upload limits, 422 for invalid user input, 429 for rate limits, and 503 for unavailable required infrastructure. AI outages are operational states, not misleading empty job responses.

API handlers do authentication/validation, invoke service use cases, and return contracts. They must not contain browser automation or long AI calls. Generated clients and backward-compatible contract checks prevent frontend/backend drift.

## Implemented inventory API checkpoint

Company watches accept a label, optional public website and a 1–720 hour interval (24 by default). Creation returns a durable discovery intent while retaining unresolved watches. Company/source edits require quoted If-Match revisions. Source creation currently accepts an explicit Greenhouse/Lever/Ashby board identifier, optional Lever EU region and confirmed_company=true; arbitrary URL discovery and generic sources are later work. Adding a source records owner confirmation, not verified network access. Company check actions return a control operation that queues or joins eligible source checks; source cooldowns and pauses remain effective.

`GET /jobs?view=all` serves unassessed inventory independently of candidate profile, with company, availability, plain-text query and stable cursor filters. Cursors are bound to their filters. Job detail includes source history links and current revision provenance. The recommended view now filters current match and possible_match results. Without a reviewed profile and matching configuration it returns matching_unavailable; All jobs remains accessible. Each job has assessment_status (assessed, stale or not_assessed), an optional current assessment/report and a separate current assessment_operation with queue/failure details. Old results are withheld from the current report. Cursors also bind to profile/model/policy/mode context, so a changed matching context requests a list reload. The portal displays current verdicts/evidence, stale/failure states and queued progress; live collection remains unverified.

## Implemented job owner actions

POST /jobs/{id}/reassess captures current profile/model/policy/mode and job revisions, including closed jobs. It joins queued/running or already-successful work and requeues a failed/blocked/cancelled current operation only on an explicit request. Optional Idempotency-Key records a durable receipt: repeating it returns the original operation without another attempt, even after terminal failure or changed configuration; using the same key for another job returns 409. A new explicit retry uses a new key. Missing profile/model mapping returns 409.

PUT /jobs/{id}/feedback accepts value (relevant/not_relevant), optional reason (maximum 2,000 characters), and expected_revision (0 for first save). Conflicts return 409. Job detail includes the latest feedback; feedback never changes the AI verdict, shortlist or preferences. Profile purge also deletes feedback and cached job explanations/notes.


## Implemented notification configuration and history

Authenticated GET/PATCH `/settings/notifications` exposes enabled, IANA timezone, local_time (HH:MM), include_empty, revision and persisted next date/UTC instant. PATCH requires the quoted If-Match revision (0 before first save); conflicts preserve stored settings. Changing timezone/time/enabled computes a future slot, while changing only the empty-summary preference preserves the scheduled instant. Saving settings does not publish a message.

GET `/notifications` returns digest snapshots and states, with descending unique local-date pagination (`before=YYYY-MM-DD`, limit 1–100). Snapshots distinguish new/baseline/reassessment counts, company totals, up to ten examples and source-error/pending-operation counts, current assessment failures, unresolved watches and matching availability. These ledger APIs are implemented; portal controls, publish testing, delivery transport and manual resend are still pending.


Notification history now includes the latest delivery attempt (state, attempt number, safe error code, server receipt ID, retry eligibility and timestamps), excluding destination/credential data. Generic operation retry rejects digest_deliver operations; ambiguous notification resend needs its own explicit confirmation flow, still pending. Saving notification settings does not test or publish immediately.
