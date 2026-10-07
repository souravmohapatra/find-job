# Data model and invariants

PostgreSQL is the system of record. Use UUID identifiers, UTC timestamptz, foreign keys, and explicit enum/check constraints. Relational columns support identity, lifecycle, indexing, and queries; versioned JSONB stores flexible extracted facts and explanations. Pydantic validates all structured payloads before persistence. No profession-specific columns or industry enum is allowed.

## Tables

| Table | Main fields and purpose |
| --- | --- |
| users / sessions | One owner account; password hash, hashed random session token, expiry and revocation. Public registration is absent. |
| profiles | Singleton row and current approved revision pointer. Database uniqueness enforces one active profile. |
| profile_revisions | profile_id, increasing revision, facts JSONB, preferences JSONB, schema version, author, approved_at; immutable after approval. |
| documents | Generated storage key, media type, size, SHA-256, extraction status, text artifact reference, extraction metadata, deletion timestamp. |
| profile_drafts | document_id, base_revision_id, proposed facts with evidence, user edits and review state. Unapproved drafts never replace active matching input. |
| companies | User label, resolved name/domain, resolution evidence/status, paused flag, default interval, discovery due time. |
| sources | company_id, adapter kind/config, verified URL, status, coverage mode, interval, due time, first complete baseline time, last success/error, cooldown. |
| discovery_runs / source_candidates | Company/query context, evidence, candidate URLs and identity, verified/unverified/rejected status, budgets and timestamps. |
| collection_runs / collection_observations | source_id, operation_id, inventory epoch, continuation cursor, observed posting identities, start/end, complete/partial/failed state, coverage/cap reasons and retries. |
| jobs | company_id, canonical identity, current revision pointer, first_seen_at, last_seen_at, availability state. |
| job_sources | job_id, source_id, external ID or normalized URL identity, first/last seen, consecutive complete omissions, availability evidence. |
| job_revisions | job_id, content hash, title, locations JSONB, remote rules, role/domain tags, description, salary facts, published_at, source evidence; immutable. |
| assessments | job_revision_id, profile_revision_id, policy version, prompt version, task-model configuration revision, requested/returned model IDs, routed endpoint when available, status, verdict, primary-function relation, coarse relevance score, structured reasons and usage. |
| job_feedback | job_id, latest user feedback (relevant/not relevant), optional reason, timestamp; feedback never silently changes preferences. |
| operation_intents | kind, stable deduplication key, parameters containing IDs, state, lease/heartbeat, attempts, timestamps and sanitized error. |
| notification_events / digests / digest_items / deliveries | Stable event keys; owner/local-date digest uniqueness; scheduled timezone/local time and UTC cutoff; event membership, snapshot, attempts/delivery state and remote acceptance ID. Membership tracks unconsumed, delivered and ambiguous events across days. |
| app_settings | Versioned non-secret notification preferences (19:00 default, IANA timezone, empty-summary option), budgets, retention configuration. |
| ai_task_configs | Immutable revisions per task: model ID, provider routing preferences, supported generation parameters, token limits, timeout, optional explicit fallback IDs; active revision pointer. No API keys. |
| inference_calls | Operation/task/config IDs, request/generation ID, requested/returned model, routed endpoint when available, token usage, estimated/reported cost, reservation, latency and safe outcome. No raw private prompts. |
| audit_events | Timestamp, actor, action, entity ID and safe metadata; no CV text, passwords, tokens, or raw AI prompts. |

Procrastinate owns its own schema and migrations. Do not modify queue internals through ORM models. Rebuildable queue records reference business operation IDs.

## Profile representation

Facts contain employment entries with original dates and precision, responsibilities, skills with evidence references, industries, qualifications, languages, and an editable professional summary. Evidence references point to document page/paragraph spans or user edits. Contact identity is stored separately from the matching facts and excluded from inference requests where unnecessary.

Calculate experience from the union of confirmed employment date intervals; never add overlapping roles twice. Missing or year-only dates produce a range/unknown instead of invented months. Keep user overrides labelled. Do not infer seniority solely from elapsed years or protected personal characteristics.

Preferences include desired role families, preferred/required capabilities, seniority direction, employment types, locations and remote eligibility, compensation with currency/period, exclusions, free-text goals, and domain mode/targets. Required fields at activation: reviewed summary and at least one desired role/function. Other fields may remain explicitly unrestricted. Matching includes an editable broad-relevance threshold, initially 30/100; inferred preferences are preferred rather than must-have. Primary-function exclusions come from user intent, not global profession blacklists. Domain labels are editable strings with normalized aliases, not a closed taxonomy.

## Identity and history

Unique source posting identity is `(source_id, external_id)` where available, otherwise `(source_id, normalized_url)`. Conservative URL normalization removes known tracking parameters and fragments, not meaningful query parameters. Across sources, merge only on identical stable ATS identity or verified canonical job URL for the same company. Similar titles alone do not merge jobs.

Hash normalized meaningful content, excluding retrieval timestamps and layout noise. Title, description, locations, remote conditions, salary, and application URL changes create revisions. Published dates are source claims, nullable and distinct from first-seen timestamps.

Availability is derived from job_sources. Three consecutive complete successful omissions mark that source's listing unavailable; any positive observation resets it. Partial/failed runs never increase omission counts. Only mark a job closed when all its known source associations have reliable unavailable evidence; otherwise use active or status-unknown. Generic/search sources cannot infer closure from missing search results. Explicit verified expiry or removal may update their association. Preserve closed jobs behind a visible availability filter.

## Transaction and index rules

- Unique immutable assessment identity: job revision + profile revision + policy/prompt version + task-model configuration revision. Retries update attempt metadata, not duplicate assessments.
- Persist collected jobs/revisions and assessment intents together. Persist a completed assessment and eligible notification event together.
- Profile activation and reassessment intent creation are atomic. Reassessment expands in batches without a huge transaction.
- Profile edits use optimistic concurrency (`If-Match` revision); reject conflicting saves with 409 and retain the user's form data.
- Index due sources, pending intents, company/first_seen job ordering, active availability, and current verdict lookups.
- Use PostgreSQL full-text search with the simple configuration for title/company/description, preserving domain terms. No embeddings required.
- “All jobs” queries begin with jobs and LEFT JOIN assessment data; they must include absent, failed, stale, and rejected assessments.
- Every asynchronous result is checked against current versions before display as current or notification selection.
- Jobs capture immutable task-model settings when queued. Record returned model/endpoint separately as execution provenance; no downloadable model digest is assumed. Editing matching-model configuration triggers reassessment; changing profile-analysis/extraction models affects future tasks unless reprocessing is explicitly requested.

## Retention

Keep approved profile revisions, normalized jobs, and assessment history until user deletion initially. Keep diagnostic fetch artifacts for seven days and operational logs/runs for 30 days by default. Delete source CV binaries and extracted raw text 30 days after successful approval unless the owner selects retention; retain reviewed facts and minimal evidence excerpts needed for explanations. Show this policy during upload. Do not delete the only pending draft input automatically.

Owner-triggered deletion must remove related live documents, drafts, facts, and personal artifacts through a documented purge operation; immutable history is not an exemption. Backups expire on their separate schedule. Backups and all persisted personal data remain private.
