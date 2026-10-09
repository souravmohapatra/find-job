# Live API validation on the deployment host

Updated: 2026-10-09. Derived from the canceled local plan at `b58706d`, preserving the subsequent execution checkpoint and medium-reasoning preference. **Deployment-only companion to FINISH_DEVELOPMENT_AND_VALIDATE.md, section 8. Do not execute this plan on the original development machine.**

The owner canceled validation on the original development network and moved this work to the deployment environment. First establish reliable API transport, request/response handling, accounting and application orchestration. Only then improve prompts, typed questions, parsing and matching usefulness. “Fine-tune” here means application and prompt iteration, not training model weights.

**Validation budget:** The owner established an initial **US$1 or 60 inference requests** validation allowance, confirmed on 2026-10-09 as an **advisory validation budget**, with the key's provider-side limit (US$5/month) serving as an outer backstop. Any single call or batch exceeding US$1 halts for owner review. The durable run ledger (`.data/live_run_ledger.json`) enforces admissions. Recorded activity on the deployment host: **2 inference attempts, US$0.000020042 known spend, US$0 held spend**, and 1 metadata GET. Remaining allowance under the advisory cap: 58 attempts, US$0.999979958.

Active models: `openai/gpt-6-luna` for profile analysis and unstructured job extraction, and TypeSafe Jev (`typesafe/jev-1.13`) for job matching judgments through OpenRouter. Jev task-boundary adapter is implemented with fail-closed typed normalization, 5-anchor relevance scoring mapped by `round_half_up(25 * native_score)` to 0..100, dynamic `domain_status`, dynamic `important_unknowns`, bounded exact evidence candidates, and per-criterion comparability checks under policy version `broad-v2`.
## 1. Scope, precedence and stop conditions

The owner reported a key in ignored root `.env` on the original machine. Do not assume that file transfers with Git or copy it into tracked files. Provision the existing key-only secret-file interface privately on the deployment host. The backend reads `JOBFINDER_OPENROUTER_KEY_FILE`; it does not automatically load `.env` or `OPENROUTER_API_KEY`.

Start from [FINISH_DEVELOPMENT_AND_VALIDATE.md](FINISH_DEVELOPMENT_AND_VALIDATE.md). Execute this companion at its section 8 after host intake, dependency portability and isolated test setup. The parent guide still requires an explicit execution assignment on the intended host; this documentation cleanup does not launch deployment. Local live execution and further local metadata probes are canceled, not waiting for a trust workaround. The earlier `@preset/job-finder` selection is superseded by the explicit Luna/Jev mappings; preset support is not a prerequisite.

Read [AGENTS.md](AGENTS.md), [CONTEXT.md](CONTEXT.md), [PLAN.md](PLAN.md), the current checkpoint of [PROGRESS.md](PROGRESS.md), [DECISIONS.md](DECISIONS.md), [IMPLEMENTATION.md](IMPLEMENTATION.md), [MATCHING.md](MATCHING.md) and the relevant sections of [VALIDATION.md](VALIDATION.md). Use source code to resolve stale implementation summaries.

Boundaries:

- Keep the existing stack, database, queue, task configuration and accounting. Add the smallest task-specific Jev adapter; no new framework, broker, vector store, SDK requirement, judge cascade, batch API or local inference service.
- Use synthetic profiles, CVs and job text. A key in `.env` is not authorization to transmit a real CV or other private local files. Do not use the real CV present in this checkout.
- Keep search and notifications mocked, fetcher access disabled, and company collection out of this exercise. A successful OpenRouter request does not establish fetcher isolation or production networking.
- Preserve the dependency-failure boundary: on any failed sync/download/pull, stop that setup path and record the original command/error/exit status. No alternate registry, certificate workaround, disabled TLS, proxy change or blind retry. Reuse installed dependencies and existing images where possible. Registry migration is not part of this task.
- For a live API TLS/connectivity failure, record sanitized diagnostics and stop live work on that path. Do not infer that VPN restrictions are the cause without evidence; do not change host networking or trust. Mocked adapter work can continue.
- Use normal Docker Compose bridge networking on the deployment host, including an isolated test database. Do not carry over `compose.test.host.yaml` or the old host-network workaround. The test database may publish only its documented loopback port; production database access follows DEPLOYMENT.md.
- Do not change the user’s `.env`, overwrite existing secrets, change remotes, rewrite history, push, deploy or send notifications. Local implementation commits after passing checks are permitted by the project guide.
- Stop paid work at the cap, on unresolved billing, on unsupported mandatory privacy controls, or if either selected model cannot be verified. Report a blocker; do not silently substitute models or weaken validation.

Authorization for live testing is already given. Do not ask again simply because requests cost money. Ask only for genuinely missing inputs or a change in scope, budget, privacy or destructive action. Continue independent offline work when a live gate is blocked.

## 2. What exists and what must change

These are source findings, not assumptions about a successful runtime:

| Location | Current behavior | Work needed |
| --- | --- | --- |
| `backend/app/config.py` | `JOBFINDER_` environment settings; key-file path; default mock mode; cached settings | A development launcher must deliberately load the private key and set process configuration before application imports. |
| `backend/app/ai/contracts.py` | Three task keys; author/model ID validator; shared chat token/pricing fields | Explicit adapter identity and compatible task/configuration validation. Reject a decision model for generative tasks and a router as a substitute for Jev. |
| `backend/app/ai/provider.py` | Chat completions, strict schema, endpoint capability lookup, spend reservations, one repair, response-model equality | Preserve the Luna path; share appropriate accounting/error primitives with a separate decision path. Do not run Jev through chat parsing or schema repair. |
| `backend/app/ai/catalog.py` | Chat model catalog cache | Do not assume inclusion in the chat catalog is necessary or sufficient for a decision model. Verify its official endpoint and pinned version separately. |
| `backend/app/ai/tasks.py` | All validation probes ask chat for `{"status":"ok"}`; generation metadata reconciles cost | Dispatch a native typed probe for Jev. Verify whether its IDs support the existing billing lookup. |
| `backend/app/ai/profile.py` | Structured `Facts`, exact quotation/provenance checks | Test Luna on the existing task before adjusting its prompt. |
| `backend/app/ai/extraction.py` | Structured `Extraction`, observed-link and exact-quote checks | Test Luna with synthetic page spans; no actual site fetch needed. |
| `backend/app/ai/matching.py` | One chat request produces `Assessment` | Implement Jev judgments and a deterministic, evidence-backed conversion into the existing assessment contract. |
| `backend/app/domain/matching.py` | Evidence validation and deterministic `category()` under `broad-v1` | Preserve policy behavior; version the new adapter/question/normalization semantics so old assessments cannot masquerade as new ones. |
| `backend/app/api/ai.py` | Authenticated Settings, immutable revisions, limits, cost acknowledgment, queued probes | Exercise these paths, not just a standalone HTTP request. Matching config edits queue reassessment. |
| `backend/app/ai/models.py` | Durable request/reservation records | Reuse; add fields/migration only if needed for decision provenance that cannot fit existing immutable records. |
| `backend/app/services/matching.py`, `backend/app/services/operations.py` | Durable assessment intents, version checks, leases and visible failures | Preserve replay/stale-result/cancellation guarantees when adding the adapter. |
| `backend/tests/conftest.py` | Migrates and truncates a `jobfinder_test*` database; forces mock mode for each test | Do not use it to run live acceptance or point it at a database whose evidence must be retained. |
| `scripts/test-backend.py` | Reads `.secrets/test_db_password`; runs pytest against `jobfinder_test` on port 55439 | Appropriate for offline regressions only. It does not enable live testing. |

Current code has useful guards already. Do not bypass its reservation, evidence, consent or immutable-version logic to obtain a green live result. Historical backend/browser pass counts in the progress log are not fresh results for this work.

## 3. Model and protocol contracts

### 3.1 GPT-6 Luna

Use the exact initial ID `openai/gpt-6-luna`, documented on the [OpenRouter model page](https://openrouter.ai/openai/gpt-6-luna). Recheck availability and endpoint metadata at execution time; a model available to a coding agent is not automatically available to the owner's API account.

Use the existing non-streaming `POST https://openrouter.ai/api/v1/chat/completions` adapter for both generative tasks. Keep JSON Schema output, local Pydantic validation and exact evidence checking. Provider capability support is endpoint-specific; use `require_parameters` and compatible endpoint selection as described in [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).

The owner subsequently permitted medium reasoning effort for Luna testing (2026-10-09). Use `reasoning.effort=medium` once current endpoint support is verified; leave temperature unset. Add only controls confirmed supported and needed by measured results. Do not switch to a decisions variant, latest alias or different model. No implicit fallback list. Record requested and returned IDs separately. If a dated returned ID differs, validate a documented exact mapping; never accept arbitrary prefixes or turn off model checking.

Use small deterministic connectivity payloads first. Then use the actual `Facts` and `Extraction` schemas. A tiny probe passing says nothing about whether the nested application schema is accepted or whether its evidence is useful.

### 3.2 TypeSafe Jev

Jev returns typed decisions rather than generated prose. OpenRouter documents `POST https://openrouter.ai/api/alpha/decisions` for plain HTTP and `/api/v1/systemone` for TypeSafe-compatible clients. Both use the OpenRouter key. This plan selects the Decisions surface with existing HTTPX; do not add a TypeSafe account or send this key to the direct TypeSafe service. See the [OpenRouter Jev guide](https://openrouter.ai/docs/guides/community/jev).

Use `typesafe/jev-1.13` initially, rechecked against the [model page](https://openrouter.ai/typesafe/jev-1.13). Do not confuse it with `typesafe/jev-router`, which routes to other models. Do not use the floating `~typesafe/jev-latest` alias during this evaluation.

The native shape is `model`, `state`, and a named `questions` map; the result has a named `answers` map. Choice uses named criteria; Noul returns a probability; Score uses ordered criteria and can return a fractional position. These are not chat messages, tool calls or `message.content`. Verify exact fields against the [TypeSafe API reference](https://docs.typesafe.ai/api) and OpenRouter’s current surface before implementation. Preserve native results alongside normalized values.

A design example for the first synthetic request, not a command to execute during plan preparation:

```json
{
  "model": "typesafe/jev-1.13",
  "state": {"test_value": "local-validation"},
  "questions": {
    "probe": {
      "type": "choice",
      "instructions": "Which criterion describes state.test_value?",
      "criteria": {
        "expected": "Exactly the string local-validation",
        "other": "Any other value"
      }
    }
  }
}
```

The production client currently has `/api/v1/` as its base. Joining `alpha/decisions` to it would produce the wrong URL. Keep fixed, reviewed endpoint constants and test the exact outbound URL, redirects disabled, and authorization restricted to the intended OpenRouter origin.

Treat these integration details as gates to verify, not invented capabilities:

1. Where decision model/version availability and pricing are authoritatively described; whether the chat endpoint catalog exposes them at all.
2. Which routing/privacy/price controls the Decisions endpoint actually honors. Do not blindly send chat `provider`, `response_format`, `max_tokens`, `temperature` or reasoning fields. Unsupported fields may be ignored, not enforced. Preserve data-collection denial and any selected ZDR requirement through documented equivalent controls; absent an enforceable equivalent, pause this adapter and ask the owner instead of silently relaxing the requirement.
3. The exact response envelope, returned model/version, provider identifier, usage keys, cost units, generation/request ID and error shapes. OpenRouter and direct TypeSafe may expose different usage fields. Missing is unknown, not zero.
4. Whether the normal generation-metadata lookup accepts decision request IDs. A 404 must not trigger another inference or erase a reservation.
5. Complete state-plus-question size limits and pricing upper bounds. Current chat estimates cannot simply be copied if decision billing has different units or fees.

The separate OpenRouter Decisions API-reference page could not be retrieved while preparing this plan. The official Jev guide and TypeSafe native reference were accessible. Re-read the live official OpenRouter contract before relying on routing or billing fields; do not fill this gap from third-party examples.

## 4. Phase A — isolate credentials, state and spending

Complete before any billable request.

1. Inspect Git status, current progress, installed interpreters and test tools, known local services and database identity. Preserve unrelated changes. Do not start by syncing dependencies or pulling images. Confirm `.env` and any proposed output directories are ignored and untracked, using metadata only in logs.
2. Create a small development-only launcher/harness, for example `scripts/validate-live-api.py`, with an explicit `--execute-live` gate and default offline/dry-run behavior. **This script does not exist yet.** Use the backend virtual environment and existing HTTPX/application functions. Do not create a second production client or bypass the ledger with curl smoke tests.
3. Prefer the privately provisioned key-only file and existing secret mount. Check existence, permissions and key availability without printing its value. If the owner supplies only a new-host `.env`, a development launcher may parse its selected key with interpolation disabled; never execute shell text. Never `source .env`, dump the environment, use `set -x`, put the key in command arguments, or include it in exceptions. Do not make dotenv conversion a requirement when the mounted key file already works.
4. Only if a temporary dotenv-to-file bridge is necessary, create a unique owner-only directory and key-only file under ignored `.secrets/` (directory mode 0700, file mode 0600, exclusive creation), set `JOBFINDER_OPENROUTER_KEY_FILE` to its absolute path for the child processes, and remove only this run's temporary secret on orderly shutdown. Do not point the setting at the whole `.env` file. Do not alter production credential precedence or overwrite another key file.
5. Set process configuration before importing settings, database or worker modules: development environment, live AI mode, mocked search and notifications, no mock AI fixture directory and no fetcher URL. Never print the database URL. If reusing a process, settings/engine caches must be deliberately reset; a fresh process is simpler.
6. Use a separate synthetic database named `jobfinder_test_live_api_<run-id>` and separate ignored document directory. Record its non-secret name. Initialize existing migrations/queue schema and a synthetic owner using existing helpers. Never point the truncating pytest fixture, browser fixture or restore scripts at this database. Never connect a live worker to the user's existing application database.
7. Use the new host's isolated PostgreSQL test container with `compose.test.yaml` and normal bridge networking, without `compose.test.host.yaml`. Verify the actual published listener is only `127.0.0.1:55439` and a host SQL connection works before using the existing test runner. A failed pull remains a blocker. Do not bypass networking failures with host networking. Keep Docker inspection narrow enough not to print service secrets.
8. Persist a run identity and remaining total allowance outside disposable test tables. Count every outbound inference POST, including rejected attempts and automatic repairs, across all phases. Metadata GETs are tracked separately. No SDK-level hidden retry loop. Use concurrency one for live validation, regardless of the normal application limit of two.
9. Set the app's daily limits no higher than the remaining total allowance. Add a small persistent run-level admission check because daily limits reset at UTC midnight and test databases can be recreated. Admit a call only if known spend plus held reservations plus the next conservative reservation stays within US$1 and the next attempt is within 60. No zero-cost assumption for an ambiguous send. Ensure every adapter's repair/retry goes through both gates.
10. Reconcile the initial run ledger and check the key's configured external spending backstop if available without displaying key material or unrelated account data. The application cap is estimated admission control, not a provider-enforced guarantee. Do not modify account limits through the API. Keep unresolved costs held and stop further live dispatch until reconciled.

The current default price ceilings reserve roughly US$0.56 for a 16k-input/4k-output chat request. They are ceilings, not the chosen model's actual price. Check current eligible prices and choose a documented conservative bound for these fixed models; do not lower reservations just to force more calls under the budget. Size limits must contain the full schema/state/questions. Never silently truncate a CV or job.

**Gate A:** No secret exposure, dedicated disposable state, correct process settings, no unrelated queue work, and demonstrated offline refusal at both request/spend limits. A database reset or restart must not reset the allowance.

## 5. Phase B — prove the non-AI harness offline

Keep prompts/questions fixed. Here, “non-AI harness” includes serialization, transport, parsing structure, accounting and state transitions; it does not include optimizing model judgment.

Implement the adapter split at the task boundary. Preserve existing immutable task revisions; an old revision without an adapter field must retain its historical chat meaning. Jev may be selected only for `job_matching`. Record the protocol, question/normalization version and requested model so both execution and replay are unambiguous. Avoid inferring arbitrary new capabilities solely from a model-name substring.

Build deterministic HTTPX transport tests for both adapters:

| Test | Required result |
| --- | --- |
| Exact host/path, auth, headers, body | Luna uses chat; Jev uses Decisions; neither leaks credentials on redirect. |
| Mock mode or absent key | Zero live requests; actionable state. Mere key presence never enables live mode. |
| Unsupported model/task/configuration | No paid dispatch; no automatic substitution or downgrade. |
| Successful complete native response | Correct normalized types, provenance, usage/cost and terminal success. |
| Unknown returned model/version | Reject visibly; retain billing; no broad prefix acceptance. |
| HTTP 200 with an error envelope, non-JSON, null/list body, missing answers or choices | Controlled error; no crash that loses the reservation, no default success. |
| 401/402/403/404/422 | Sanitized actionable state, no futile automatic retry. |
| 429 and Retry-After | Persist cooldown and bounded retry intent; never loop immediately. |
| Timeout, disconnect, 5xx/overload | Potential charge remains held; no duplicate send while billing is unresolved. |
| Missing/invalid/negative/non-finite cost | Unknown billing and blocked subsequent dispatch; never free. |
| Budget and concurrency admission | Rejected before network I/O, including retries/repairs. |
| Invalid evidence or schema | Visible failure with paid attempt retained; never a rejection of the job. |
| Oversized input/output or truncation | Explicit failure; no partial result claimed complete. |
| Cancellation, redelivery and stale versions | No duplicate completed call; obsolete work cannot publish a current assessment. |

For Luna additionally cover incomplete nested JSON, refusal, empty content, extra fields, wrong scalar types, non-stop finish reason, nullable fields and exactly one bounded schema/evidence repair using the same model/configuration. Categorize errors: model mismatch and refusal should not be blindly treated as a repairable syntax error. Record and fix observed defects without weakening the output contract.

For Jev additionally cover required question IDs, matching answer types, unknown choice values, missing/extra option probabilities, out-of-range or non-finite numbers, booleans masquerading as numeric values, wrong score-level keys and inconsistent selections. Use a documented floating tolerance for probability sums; do not silently renormalize bad responses. Keep protocol parsing separate from domain interpretation. Tolerate documented optional metadata absence while requiring the fields used for decisions/accounting. A typed-contract error does not get a chat repair prompt.

Use synthetic provider-shaped responses; label them authored fixtures. Do not call them live captures. Add sanitized real captures only after a successful probe, and only from synthetic payloads. Redact credentials, request headers, cookies and arbitrary error bodies before saving anything.

**Gate B:** Meaningful mocked tests pass for both transports and the shared budget/state logic. A small matching adapter and probe dispatch exist. Production code is not bypassed by a standalone demonstration client. No prompt-quality claim yet.

## 6. Phase C — bounded live connectivity and schema checks

Suggested allocation: at most 6 successful probes, with up to 4 further attempts held for necessary diagnosis. This is part of the overall 60, not an extra allowance. Stop on the first unresolved failure and diagnose offline before another paid attempt.

1. Revalidate the fixed model/protocol/pricing/privacy contracts. Start with an empty synthetic inventory and no control/fetch/notify worker. Saving matching settings queues reassessment; inspect pending operations before starting anything.
2. Run one tiny Luna structured-output probe through the real configured adapter and ledger. Check the HTTP result, response envelope, returned ID, exact parsed result, cost/usage, latency and persisted terminal state.
3. Run one tiny Jev Choice probe through its native adapter and the same admission/accounting guarantees. Check native answer shape and normalization, actual served version and cost. Do not read `choices[0].message.content` from this result.
4. Use the existing authenticated `/api/v1/settings/ai/validate` operation with `acknowledge_cost: true` to prove task-specific probe dispatch. Make the first probes use this path where practical so the same call covers transport and operation handling. Test profile and extraction mappings independently even though they use the same model.
5. Send one minimal synthetic CV through the actual profile schema and one synthetic job page through the actual extraction schema. These are schema-compatibility checks with manually checked expected fields, not a quality benchmark.
6. Verify Settings and usage display agree with the durable ledger. Billing reconciliation, if needed, must not resubmit inference. Inspect only sanitized structured diagnostics; do not solve schema problems by dumping raw provider exceptions containing payloads.

If a probe fails, classify it before touching the prompt: credential loading, TLS/connectivity, endpoint/model access, unsupported schema/parameter, envelope parsing, billing/provenance, queue execution or semantic output. Fix and prove the relevant case offline, then rerun only the affected probe within the remaining allowance.

**Gate C:** Both real API surfaces work through application accounting; Luna accepts the actual generative schemas; validation operations finish truthfully. Record “transport passed” separately from “semantic evaluation pending.”

## 7. Phase D — Jev matching and explanation contract

Do not ask Jev only “is this a good job?” and discard the existing policy. Preserve the existing assessment dimensions and let `category()` derive `match`, `possible_match` or `not_match`. All jobs remain visible; both shortlist categories remain eligible for the digest.

Use the reviewed professional profile/preferences and normalized job spans from `matching.task_input()` as state. Keep original CV quotations and contacts out. Each question must name the relevant state fields and include its own criteria. Questions in the same request are evaluated independently; one cannot consume another answer from that request. This follows the [TypeSafe state model](https://docs.typesafe.ai/concepts/state). Apply consistency rules after all answers are validated.

Start with this explicit application design, then adjust only with failing examples:

| Existing assessment field | Jev judgment / deterministic mapping |
| --- | --- |
| `relation` | Choice: aligned, adjacent, unrelated, unclear. Judge primary duties against desired/excluded functions, not a global title blacklist. |
| `relevance_score` | Separate evidence-sufficiency Choice plus an ordered Score. Initial five rubric anchors: 0 no meaningful overlap, 25 limited overlap, 50 credible partial transfer, 75 substantial overlap with gaps, 100 very strong overlap. After verifying native levels are 0–4, map the score by `round_half_up(25 * native_score)` to 0–100. Insufficient evidence produces null. This is a selected heuristic mapping, not a provider probability. |
| `plausible_connection` | Choice: supported, unsupported, unknown. Only supported with valid evidence becomes true; do not coerce an ambiguous probability to true. |
| Each preference result | Choice: met, not_met, unknown, evaluated against its actual ID, strength and description. Separate comparability/evidence checks; missing or incomparable information stays unknown. |
| `domain_status` | Choice: met, not_met, unknown against explicit domain intent; only focus-mode conflict is a hard rule. |
| `important_unknowns` | Explicit judgment plus required-criterion/domain unknowns; preserve uncertainty independently of score. |
| Primary-function label, reasons, transferable points, gaps | Deterministic descriptions and exact selected evidence as specified below. Jev does not produce free-form rationale. |

The 30/100 threshold remains application relevance, not `P(good job) >= 0.30`, not model confidence, and not “30% of requirements met.” Test the chosen score conversion at 29/30 and 59/60 offline. Version this normalization so future changes cannot silently reuse old results. Preserve the configurable threshold.

Choice/Score confidence and the probability distribution are different fields; store them without reinterpreting one as the other. The vendor explains this distinction in [TypeSafe confidence](https://docs.typesafe.ai/confidence). A high score with uncertain or missing evidence must not become a confident match. Do not invent a supposedly calibrated confidence threshold. Start with explicit unknown options and consistency rules; record confidence for evaluation. If observed ambiguous distributions require an action threshold, document and test it as a local heuristic and retain the raw judgment.

### Evidence and explanations without a second judge

The existing `Assessment` requires exact source references; `Evidence.quote` is at most 1,000 characters. A typed choice cannot satisfy that requirement by inventing prose.

1. Prepare a bounded set of deterministic quotation candidates from the supplied spans, each carrying an immutable candidate ID, original span ID and exact substring. Use sentence/paragraph boundaries, preserve offsets, and respect the quotation length bound. Keep the complete original state subject to input limits; evidence candidates are an index, not permission to silently truncate the document.
2. For decision dimensions requiring support, let Jev select from these candidate IDs with an explicit `insufficient_evidence` option. Split source-specific selections where necessary: duties require `job:description`; relation additionally requires desired/excluded-function evidence; relevance/plausibility require both sides; a known preference outcome requires the exact preference ID plus comparable listing evidence. Resolve selected IDs in code, never accept model-generated quotations or URLs.
3. Bound candidate counts and total state/question size. Do not create every possible cross-product of excerpts. Reuse the same candidate pool and small source-specific Choices. If the contract cannot fit, fail with an explicit scope/size limitation rather than silently dropping criteria. Do not add a general retrieval framework.
4. Render factual templates from the normalized decisions and selected evidence: function relationship, coarse overlap, explicit criterion conflicts and unknowns. Label these as application explanations of the assessment, not verbatim Jev reasoning. A primary-function display label can be derived from selected duty text, shortened for display with the full evidence retained. No invented capability, qualification or claim of detailed model reasoning.
5. Cite only evidence that supports the displayed assertion, not arbitrary snippets chosen just to satisfy the validator. Exact substring validity proves provenance, not semantic entailment; manually check supporting meaning in the small evaluation set.
6. Optional reason/gap/transfer lists may remain empty when unsupported. A useful result must still explain its function judgment, overlap and uncertainty using the evidence-backed fields. Do not fill arrays with generic boilerplate or claim all explanation requirements pass if the resulting UI is uninformative.
7. Run the existing `validate()` and `category()` after conversion. Contradictory/unsupported evidence is an assessment failure, never fabricated `not_match`. Do not loosen evidence constraints to accommodate Jev. Do not add a Luna decision fallback or explanation call without a separately justified need; the initial design uses only Jev for matching judgments.

Where a new policy/adapter version affects persistence, ensure the durable assessment identity includes it and reassessment produces a new immutable result. If an adapter version cannot fit existing version fields, make the smallest explicit schema change and migrate/test it. Keep existing chat assessments readable as historical results.

**Gate D:** Offline normalization/evidence tests pass, a simple live Jev job case can produce a valid current assessment with a useful explanation, and all original deterministic policy invariants remain intact. An inability to provide adequate evidence is a blocker to calling matching complete.

## 8. Phase E — prompt and semantic evaluation

Only after the harness gates pass, tune the prompts/questions. Use a small authored set with expected outcomes and evidence IDs declared before requesting the model. Keep gold labels and reviewer notes out of the outbound payload. Do not use Luna to grade Jev or Jev to grade Luna in this effort.

Suggested first evaluation: 4 CVs, 4 extraction pages and 12 job/profile pairs, one call per case where possible. Allocate at most 20 further attempts for targeted prompt revisions and repairs, and retain 10 for the integrated journey. The suggested allocation totals at most 60 with Phase C; the spend ceiling can stop it sooner. Gate D's live case should reuse an evaluation case rather than add an uncounted request. Account for any additional calls explicitly before dispatch.

Profile cases:

1. A short clear CV with roles, dates, skills and exact source evidence.
2. Missing/overlapping dates and an ongoing role; no invented experience total or zero-years assumption.
3. A different profession and industry; no strategy/finance defaults or inferred future preferences.
4. Synthetic contact details and an embedded instruction attack; contacts minimized, data never followed as instructions, no fabricated credentials or `origin=user`.

Extraction cases:

1. A single open vacancy with complete known fields and an observed detail URL.
2. Multiple vacancies with distinct observed links and partial optional information.
3. A closed posting, talent pool and explicit no-vacancies text; do not invent open vacancies.
4. A page containing instruction injection, an unobserved link and uncertain employer/status; invalid claims fail visibly or remain uncertain under the existing extraction contract.

Matching cases must cover at least:

| Case | Expected behavior |
| --- | --- |
| Strong aligned role, evidenced requirements | Match when substantial overlap and no important unknowns. |
| Credible adjacent role around broad relevance boundary | Possible match, preserving manual review. |
| Substantial skill gaps with plausible transferable overlap | No automatic rejection merely for missing preferred skills. |
| New industry under open/expand | Familiarity is not a hard filter. |
| Same industry but clearly unrelated primary function | Not match despite shared keywords. |
| Explicit required criterion with evidenced comparable conflict | Not match; cite the requirement and conflict. |
| The same criterion marked preferred | No hard rejection solely from that gap. |
| Missing salary or incompatible currency/period | Unknown, not below minimum. |
| Remote label with no eligibility/location proof | Unknown; do not infer work authorization. |
| Focus-domain conflict versus unknown domain | Evidenced conflict rejected; missing domain stays uncertain. |
| Sparse description with plausible connection; separate unreadable input | Possible match for valid uncertainty; assessment error for unreadable/unsupported input. |
| Another target profession plus injected job instructions | Function rules adapt to the profile; injected instructions do not change policy. |

Use paired variants within these fixtures; not every variant needs another live call. Exercise precise threshold boundaries and policy permutations offline. Include a small held-out portion: initially reserve one CV, one extraction page and four matching pairs from prompt editing. Budget their first evaluation within the allocations above.

For each failure record the stage: transport, response structure, local contract, evidence, category policy or model judgment. Fix the responsible layer. Change one prompt/question/schema dimension at a time, increment its version, and rerun only affected development cases before the held-out cases. At most two deliberate prompt revisions initially; if important failures persist, report the limitation instead of launching an unbounded tuning campaign.

Acceptance is not a 90%-precision leaderboard or an exact wording match. Require all consumed outputs to pass schema/evidence validation, no invented profile facts in these checked examples, no false hard exclusions from unknown facts, broad inclusion of the authored transferable examples, and clear function-boundary handling across professions. Report exact case results and repair rate, including failures and abstentions. A dozen jobs cannot establish general accuracy or calibration.

**Gate E:** The authored acceptance examples pass or each remaining semantic limitation is explicitly listed as a blocker. Do not weaken the examples, threshold or validations merely to turn failures green.

## 9. Phase F — integrated application journey and regressions

Use the dedicated live-validation database. Keep external source collection and notifications mocked. First exercise services/operations directly with exact operation IDs; then verify the real worker/API/portal path on the same synthetic scenario within the remaining budget.

1. Configure the three mappings through authenticated Settings with the correct optimistic revision headers. Saving a configuration must not itself send paid requests. Changing matching configuration must create the expected bounded reassessment intent.
2. Upload a synthetic CV with explicit live-analysis consent. Let Luna produce a draft, inspect evidence and unknowns, make a review edit, and activate the reviewed revision. No matching may use the unreviewed draft.
3. Feed a synthetic cached page into the existing extraction handoff and run Luna extraction. Preserve employer/open-status/link/coverage checks. Also seed deterministic ATS-style postings through existing fixture/inventory helpers to prove collection is independent of AI. No website fetch is necessary or authorized by this step.
4. Run Jev for a minimal aligned, adjacent, unrelated and ambiguous set. Verify persisted input/configuration/policy/adapter identities, explanations and current results in API and portal. All jobs includes rejected and failed/unassessed entries; Shortlist includes both match and possible-match.
5. Enable only the required worker queue at concurrency one and explicitly dispatch selected intents. `app.tasks.worker` dispatches pending operations on startup; inspect the dedicated queue first. Do not run the general minute control scheduler over an existing inventory or let a mode/config change fan out into unbudgeted calls.
6. Complete one real Procrastinate worker round trip. Verify its persisted operation result after the HTTP response, not just an API 202. Replaying a completed intent must not charge again. Use mocked responses for destructive race/timeout injection instead of spending money to manufacture failures.
7. Verify profile/model/job changes make prior results stale; only the new current result is eligible. A failed or stale result cannot become a digest entry. Check the existing digest eligibility logic offline; do not send a live notification.
8. Stop processes started for this run; keep the ledger and sanitized evidence available. Remove this run's temporary key file, preserve the owner's `.env`, and leave no background live worker. Retain the synthetic database until the evidence has been summarized; deleting it is not needed for completion.

Existing regression commands, run from the repository root after confirming the disposable offline test database is safe:

```bash
python3 scripts/test-backend.py tests/test_ai.py tests/test_matching.py tests/test_assessments.py tests/test_matching_reconciliation.py tests/test_extraction.py tests/test_extraction_pipeline.py -q
backend/.venv/bin/ruff check backend/app backend/tests
backend/.venv/bin/ruff format --check backend/app backend/tests
```

Run the full backend suite after the adapter/accounting changes stabilize:

```bash
python3 scripts/test-backend.py -q
```

Run strict mypy using the backend project configuration and check any migration against its disposable database. Validate the new launcher and its budget/secret handling too. Adapt commands to actual installed tools; do not download replacements after a dependency failure. These offline commands do not constitute live proof.

If API contracts or frontend Settings need changes, regenerate existing client types and run the affected frontend checks/build before browser tests. Follow the repository's existing browser setup; do not point its auto-clearing mock database fixture at the live database or call mock browser success live acceptance. Keep frontend files, assets and dependency caches stable during Playwright. Do not download a missing browser after a blocked fetch without new instructions. A blocked browser gate must be reported separately from working backend live calls.

**Gate F:** A reviewed synthetic CV and job inventory pass through both real model adapters and the real operation/worker path, with portal verification or an explicitly outstanding portal gate; affected offline regressions pass. No production, real-source or device-notification acceptance is implied.

## 10. Evidence, checkpoints and handoff

Update [PROGRESS.md](PROGRESS.md) after each meaningful batch, immediately on a blocker, and before handing back. Record actual checks and limits in [VALIDATION.md](VALIDATION.md). Update matching/design documentation when the implemented contract changes. Keep this plan's completed/pending checklist truthful; keep the parent deployment guide aligned with actual results without expanding scope.

Keep a small sanitized run record under an ignored `.data/live-api-validation/<run-id>/` directory. Persist the cumulative budget record across restarts and test-state replacement; do not use a fresh run ID to reset the owner's total allowance. Commit only reviewed synthetic fixtures and aggregate evidence, not credentials or raw HTTP logs.

Per attempt, record: run/case ID, commit, phase/task, protocol, requested/returned model, provider if supplied, immutable configuration and prompt/question/schema/normalization versions, request/operation IDs, input fixture hash, latency, HTTP/error classification, parsing/evidence/domain outcome, reported usage/cost or retained reservation, repair/retry linkage and remaining allowance. Separate provider-reported cost from estimates. Do not put raw prompts, CV data, authorization headers or arbitrary provider errors in progress documents.

Minimum final table:

| Gate | Result | Evidence / remaining issue |
| --- | --- | --- |
| A: isolated configuration and cumulative budget | Passed | Offline refusals, disposable test DB, and `--execute-live` bridge proven in launcher (`scripts/validate-live-api.py`). |
| B: offline harness and native parsers | Passed | 329 backend tests passing offline; MockTransport covers chat and Decisions protocols, 5-anchor scoring, half-up mapping, candidate bounding, focus-domain checks, comparability, and failure modes. |
| C: Luna and Jev live protocol/schema checks | Open | Initial synthetic transport probes passed (run `20261009_142304`: Luna chat and Jev Decisions, US$0.000020042 spend, 0 held spend); actual generative profile and extraction schemas remain pending. |
| D: Jev evidence-backed assessment conversion | Open | Phase D adapter implemented under `broad-v2` / `matching-decisions-v2`, 5 anchors, `round_half_up`, bounded candidates, focus-domain enforcement and comparability; tested offline. Live Jev semantic assessment remains pending. |
| E: small semantic fixture evaluation | Pending | Evaluation dataset and target rubric pending. |
| F: real worker/API/portal integration | Pending | Deployed end-to-end journey pending. |
| Offline regressions and required frontend checks | Passed | 329 backend tests, 7 firewall transaction tests, 9 launcher unit tests passing offline. |
| Spend, request count, unresolved reservations | Recorded | 2 inference attempts, US$0.000020042 known, US$0 held spend in `.data/live_run_ledger.json`. 58 attempts / US$0.999979958 remaining under advisory validation cap. |
| Live workers stopped and temporary key removed | Verified | Temporary bridge removed on orderly shutdown in every live launcher run; verified no leftovers. |
The final report must state exact passes/failures, model versions actually used, request count and total known/held spend, any stopped stage and its next action, commit IDs, and remaining deployment gates. A successful response alone is not matching acceptance. A correct mocked parser alone is not live API acceptance. Reaching the spending cap is a bounded checkpoint, not permission to declare unfinished work complete.

## 11. Instructions to the executing agent

Work in order: isolate state and enforce the budget; build and test the harness; prove both native API contracts; complete Jev's evidence-backed policy adapter; tune against the small synthetic cases; then prove the real worker/API journey. Keep each change reviewable. Diagnose observed failures before adding features. Preserve all-jobs access, uncertainty, privacy, budget accounting and current/stale-result guarantees throughout. Return to the parent deployment guide after this API phase; execute only within the owner's deployment-host assignment.


## Historical local execution checkpoint — 2026-10-09

Started from b58706d. The first local, unauthenticated model-endpoint metadata GET failed TLS certificate verification (`httpx.ConnectError`, diagnostic exit 2). The owner canceled execution on this network; no inference, credentials transmission or spend occurred. The earlier intention to continue offline launcher/budget work is superseded by the deployment handoff. No launcher implementation is present in the tracked changes at cleanup. Jev's mandatory privacy/routing contract remains unverified because its linked official Decisions reference could not be retrieved. Public model listings alone do not clear this gate.
