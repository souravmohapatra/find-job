# Profile analysis and matching

## AI integration and task routing

Use OpenRouter for every LLM call. Implement one backend HTTPX client for `POST https://openrouter.ai/api/v1/chat/completions`, wrapped by a task dispatcher and validated Pydantic contracts. API keys stay in server-side secret files. Do not deploy a local model server. [OpenRouter API reference](https://openrouter.ai/docs/api/reference/overview).

Model selection is independent per task:

| Task key | Purpose | Initial model |
| --- | --- | --- |
| `profile_analysis` | Convert extracted CV text into an evidence-backed review draft, including chunk merge | Unset; choose later |
| `job_extraction` | Convert unfamiliar public career/job-page text into structured listing candidates | Unset; choose later |
| `job_matching` | Assess a listing against the reviewed profile and preferences | Unset; choose later |

The same model may be assigned to multiple tasks, but no global model is silently assumed. Any future LLM task must declare a task key and receive an explicit mapping. Deterministic source discovery/ATS parsing does not require an LLM. A separate judge is not required initially; job_matching itself performs the rubric-guided assessment.

Store immutable task configuration revisions: exact OpenRouter model ID, provider-routing preferences, schema/prompt version, supported sampling/reasoning parameters, input/output token limits, timeout, and optional explicit fallback models. Settings exposes these per task. No model IDs are selected in this design. An unmapped task is visibly `configuration_required`; direct collection and all-jobs browsing remain operational. The app must not use an account-default or auto-router model when no task model is set.

Use non-streaming structured output requests with `response_format` JSON Schema and `provider.require_parameters=true`. Validate endpoint/model support when a mapping is configured and again when a capability error occurs; the same model can have differing endpoint capabilities. Validate every response locally even with strict mode. Unsupported parameters must be omitted by a documented capability policy or reported as incompatible, never silently weakening the schema requirement. [Structured output support](https://openrouter.ai/docs/guides/features/structured-outputs).

Default model fallback list is empty. OpenRouter may route the selected model among endpoints that meet configured capability/privacy restrictions; record the actual endpoint when exposed. An optional per-task fallback list must be explicitly configured and validated under the same restrictions, with the model actually used recorded. Neither response-repair nor retry may silently select a different model. [Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

## Budgets, failures and provenance

Start with two concurrent requests, a 120-second timeout, output cap 4k tokens and input target up to 16k tokens, bounded by the chosen model's combined context window. Reasoning tokens and provider minimums count toward budgeting where applicable. Set temperature to zero only where supported; supported reasoning controls are task-specific. CV review has priority over historical reanalysis.

Default app guardrails: 500 calls/day and an editable USD 5/day estimated spend ceiling, with per-task usage reporting. Reserve an upper-bound estimate transactionally before dispatch using configured token caps and endpoint pricing ceilings; include retries, chunk merges and repairs. If pricing or consumption is unknown, retain a conservative reservation and pause affected work rather than assuming it was free. An OpenRouter account/key spending limit is the external backstop; app estimates alone are not a guarantee of the final bill.

Record request/generation ID, requested and returned model, endpoint if available, configuration/prompt/schema revision, token usage, estimated/reported cost, latency and outcome. No weight digest or perfectly reproducible hosted inference is assumed. Reconcile reported cost when available without exposing raw prompts in logs.

Bound retries for 429/5xx/timeouts and obey Retry-After. Authentication errors, insufficient credits, model removal or incompatible schema settings pause the affected task with an actionable state. Ambiguous timed-out requests can still incur charges; preserve their reservation if retrying. One schema-repair attempt uses the same task configuration and counts against the budget. No tools, model-executed code, autonomous browser agents or model authority to submit applications.

## Data handling

CV parsing and original files stay on the Ubuntu server. Profile analysis sends extracted CV text to OpenRouter and its routed model provider; job matching sends the reviewed professional profile/preferences and job content. Strip unnecessary contact details and identifiers before sending, retaining work evidence needed for the task. This minimizes data; it is not a promise of anonymization. Explain the flow at upload and in Settings. Do not send the original file to a document-processing plugin.

Default `provider.data_collection=deny`; offer an explicit ZDR-only routing option in Settings, and never relax the selected restriction on fallback. Provider policy filtering does not make inference local or establish that every provider's terms are identical. Do not enable prompt logging plugins. [Routing/privacy controls](https://openrouter.ai/docs/guides/routing/provider-selection), [provider policies](https://openrouter.ai/docs/guides/privacy/provider-logging).

## CV ingestion and review

Accept text PDF, DOCX, and UTF-8 TXT, up to 10 MiB and 50 pages where applicable. Check actual file type, cap expanded DOCX content and extracted text, and run parsers in a bounded subprocess with no external-resource fetching. Reject encrypted files, macros/unsupported formats, or malformed documents with actionable errors. Image-only PDFs request a text version; OCR is deferred explicitly.

Store uploaded files with generated names in a private volume. Extract page/paragraph-labelled text, then ask the model for facts with source spans. Validate evidence references and display unknown/inferred entries for review. A replacement CV creates a draft against the current revision; show a field-level comparison and preserve user changes until explicitly accepted. Review and save activates a new immutable revision. No assessment uses an unreviewed draft.

A long input that exceeds the configured cap must be chunked using deterministic section/page boundaries with a final validated merge, or reported as incomplete. Never silently truncate a CV or job and claim full assessment. Keep original evidence references through chunking.

## Domain diversification

Default to `open`: consider any sector where relevant capabilities transfer. Setup makes the choice visible and editable before profile activation.

- `focus`: only selected target domains; a confirmed domain conflict is a required-criterion failure, and unknown domain yields uncertainty.
- `expand`: selected domains receive preference, but credible transferable roles elsewhere remain eligible.
- `open`: industry familiarity is explanatory context, not a ranking penalty or rejection rule.

The candidate's past domains never populate mandatory filters automatically. Diversification changes assessments for the existing company inventory; it does not automatically add companies. Explicit exclusions still apply.

## Broad-shortlist policy

The user wants a wide net and manual review, not highly optimized ranking. Roughly 30% overlap is enough to surface a plausible role. Implement this as a configurable heuristic relevance threshold, initially 30 on a 0–100 scale; it is not a calibrated probability, a count of keyword matches, or a promise of candidate success. Use the score only as a coarse inclusion aid. Do not tune a high-precision recommender.

The key boundary is the role's primary function relative to the user's desired role families. For the illustrative strategy profile, strategy, commercial planning, business transformation and credible adjacent work may qualify with substantial gaps. Primarily data-analysis or legal-practice roles do not qualify just because the employer/industry or a few words overlap. These exclusions derive from this profile's intent, not a global job-title blacklist.

The model returns:

- Primary job function with cited duties, and relation to desired functions: `aligned`, `adjacent`, `unrelated`, or `unclear`.
- A coarse relevance score from 0 to 100, or null when there is insufficient evidence. Anchors: 0–29 little meaningful overlap; 30–59 credible partial/transferable overlap; 60–100 substantial overlap. Do not imply precision within a band.
- Each preference ID with `met`, `not_met`, or `unknown`, supported by listing/profile evidence.
- Transferable capabilities, up to three reasons to consider the job, and up to three gaps/unknowns.

All inferred preferences default to preferred, not required. Only an explicit user must-have or deliberate focus-domain mode can create a hard constraint. Missing skills, a new industry, seniority stretch and missing salary do not automatically reject a role.

The application derives the category in this order:

1. Evidenced primary-function mismatch produces `not_match`, even if generic keyword overlap or the score is high.
2. An explicit user must-have with evidenced conflict produces `not_match`.
3. Aligned/adjacent function and relevance at least the configured threshold produce a shortlist entry: `match` for substantial overlap without important unknowns, otherwise `possible_match`.
4. Unclear function or insufficient detail with a plausible role-family connection produces `possible_match` for manual review. Unsupported model output or unreadable job content is an assessment error, not a speculative match.
5. Evidenced little relevant overlap below the threshold produces `not_match`. All such jobs remain accessible in All jobs.

Both `match` and `possible_match` are shortlisted and included in daily digest eligibility. Unknown required facts remain visible and can produce a possible match; unknown salary is never interpreted as below the minimum. Compare salary only when currency/period are comparable. “Remote” alone does not establish location or work-authorization eligibility. Validate evidence spans; a score cannot override an unrelated function or fabricate qualifications.

See [DEVELOPMENT_EXAMPLES.md](DEVELOPMENT_EXAMPLES.md) for representative strategy/analyst/legal boundaries. Similar logic must work for any candidate profile.

## Reassessment and display

Reassess all active jobs in batches when profile or matching policy changes. Reassess changed job revisions. Unchanged observations reuse current assessments. Historical/closed jobs can be reassessed on request.

Results from an obsolete revision remain historical. While a current assessment is pending, the portal can show the previous explanation labelled outdated; it must not send a new-match alert from that stale result. AI failure leaves a job unassessed and visible, not rejected.

Default Shortlist view includes `match` and `possible_match`, newest first without fine-grained score ranking. Both categories are eligible for the daily ntfy digest. User relevance feedback is recorded for evaluation and inspection; it never silently retrains a model or rewrites preferences.

## Notification eligibility

For each newly observed non-baseline job, create at most one new-job event when it first enters the current shortlist. Include a profile revision in eligibility evaluation, but use a job-level event key so later preference edits do not generate repeat new-job alerts. Initial inventories and newly added source inventories appear as separately labelled baseline counts/links in the next scheduled digest, not an immediate alert or a claim of newly posted jobs. Policy/profile changes are silent at individual-job level; the next digest may show a separately labelled reassessment summary. Changes/reopenings are visible in the portal and silent by default. A UI setting can enable these event types later without changing collection.

## Validation scope

Use a small set of understandable synthetic examples to check broad inclusion, clear function exclusions, uncertainty and no invented experience. Include transferable roles at roughly the 30-point boundary. No 90% precision requirement, extensive tuning dataset or model-ranking exercise is part of v1. Keep schema, evidence, privacy, task-routing and reliability checks; these verify correct operation rather than optimize suitability judgments. Exact OpenRouter models remain undecided.

## Implemented configuration defaults and current limits

The first provider slice is implemented and tested with synthetic HTTP transport only. Immutable task revisions capture model/routing/limits; uploads also capture mode and consent, preventing a later mock-to-live switch from sending an unconsented document. Changed matching settings persist a reassessment intent, whose inventory handler is still pending.

Selected editable routing ceilings are USD 20/million input tokens, USD 60/million output tokens, and USD 0 per-request fee. These are conservative maximum prices for routing/reservation, not claimed prices for any chosen model. Reserve the full configured input/output caps, check endpoint capabilities and pricing before dispatch, enforce the ceilings in `provider.max_price`, and preserve data-collection denial/ZDR settings for explicit fallbacks. Cache read/write prices must fit the input ceiling too. See [OpenRouter price-routing documentation](https://openrouter.ai/docs/guides/routing/provider-selection).

A conservative UTF-8 byte bound including schema/framing rejects oversized inputs visibly instead of truncating them; chunk/merge is not implemented. A second complete-input request is the only schema-repair attempt. Unknown billing (including transport timeouts) pauses further requests until reconciled; Retry-After cooldowns are persisted for explicit rate-limit responses. A key-level spending limit remains necessary as the external billing backstop. Generation metadata reconciliation is available through the API; UI recovery and verified resolution without a generation ID remain follow-up work.
