# Plain-language product refinement review

Date: 2026-10-12. Application baseline: `e6b1fa9`.

## Decision and scope

**The website currently speaks to its developer in several important journeys. Replace implementation terminology with the user's task, explain the consequence of each action, and put installation controls behind an explicitly technical section.** The issue includes backend-generated explanations and errors, not just React labels.

This document is an implementation-ready copy specification, not an implementation. No application files, services, credentials, models or notification settings were changed. Review evidence comes from all frontend feature files, the shared shell/error handling, backend messages reaching those surfaces, matching explanation generation, notification generation, and the product/development Markdown records. No fresh browser session, deployment or live request was run for this review. Existing browser observations remain in [UIUX_REVIEW.md](UIUX_REVIEW.md); engineering defects remain in [EXTERNAL_REVIEW.md](EXTERNAL_REVIEW.md).

The audience is a person looking for work who has no software-development knowledge. They should be able to upload a CV, correct their experience, describe their next job, follow companies, understand results and receive a summary without learning about queues, revisions, adapters, API credentials or deployments.

### How to implement this specification

- **P1:** resolve before relying on the affected journey; current wording can mislead, block recovery, conceal a consequence or expose internal data.
- **P2:** required refinement; current wording adds avoidable effort or makes the app feel unfinished.
- **Copy:** replace presentation text without changing the underlying product meaning.
- **Behaviour:** the specified text requires a state distinction, control, formatter or API field. Implement that prerequisite with the copy. Do not publish a promise that the existing behaviour cannot support.
- Text in the **Replacement** column is the exact intended visible copy. `{variables}` are substituted values, never literal interface text. Quoted labels are case-sensitive. “Remove” means render nothing in that location.
- Preserve API keys/enums, database values and policy semantics. These changes apply to their presentation. Do not perform global replacements in stored data.
- Do not rewrite company names, job titles, original job descriptions, the user's own answers or verbatim supporting quotations. Plain-language presentation must not alter evidence.
- Use sentence case and British English consistently: “Analyse”, “organisation”, “recognised”. Retain familiar product labels: **Jobs**, **Companies**, **Profile**, **Settings**, **Shortlist**, **All jobs**, **Sign in**, **Sign out**. Do not rename the automatically generated Shortlist to “Saved jobs”; there is no manual save-to-shortlist feature.

The exact proposals below take precedence over generic style preferences. They retain the agreed broad shortlist, uncertain results, separate experience/preferences, optional industry exploration and independent checking/notification schedules.

### Review index

Seventeen change areas: **11 P1 and 6 P2**. P1 is usability/consequence priority here, not an engineering vulnerability rating.

| Area | Priority | Exact specification |
| --- | --- | --- |
| Shared terminology | P2 | [RF-01](#rf-01) |
| Sign-in and preview branding | P2 | [RF-02](#rf-02) |
| Setup and empty lists | P1 | [RF-03](#rf-03) |
| Job filters and status | P1 | [RF-04](#rf-04) |
| Match explanations | P1 | [RF-05](#rf-05) |
| Company setup | P2 | [RF-06](#rf-06) |
| Finding job pages | P1 | [RF-07](#rf-07) |
| Technical website controls | P2 | [RF-08](#rf-08) |
| CV upload and consent | P1 | [RF-09](#rf-09) |
| Experience and preferences | P2 | [RF-10](#rf-10) |
| Saving and conflicting edits | P1 | [RF-11](#rf-11) |
| Deletion and storage | P1 | [RF-12](#rf-12) |
| Settings organisation | P2 | [RF-13](#rf-13) |
| AI choices and cost | P1 | [RF-14](#rf-14) |
| Spending and charge recovery | P1 | [RF-15](#rf-15) |
| Notifications | P1 | [RF-16](#rf-16) |
| Errors and background progress | P1 | [RF-17](#rf-17) |

<a id="rf-01"></a>

## RF-01 · P2 · Establish one vocabulary throughout the app

**Locations:** [inventory](frontend/src/features/inventory), [profile](frontend/src/features/profile), [settings](frontend/src/features/settings), [backend operation messages](backend/app/services/operations.py).

Apply this vocabulary to navigation, labels, help, errors, announcements and notifications. Context-specific sentences below override a mechanical word substitution.

| Current terminology | Replacement / precise usage |
| --- | --- |
| Company watch / watched company / watchlist | “Company you follow” / “Companies you follow”. Use “Follow company” for the action. |
| Collected jobs / inventory / collected roles | “Jobs found”. Keep “All jobs” as the view name. |
| Source | “Job page” when referring to a website being checked. Use “Job website” for its provider/platform. |
| Source discovery | “Find job pages”. Use “Job page search history” for its history. |
| Assessment / assess / reassessment | “Match check” / “Check match” / “Check match again”. A result section is “How this job fits”. |
| Queued | “Waiting to start” or the task-specific sentence in RF-17. |
| Revision | “Saved version” only in comparisons. Hide revision numbers in normal use. |
| Domain / domain mode | “Industry or field” / “Industry preferences”. Website domain names remain “Website address”. |
| Functions | “Types of work” in preferences; “Main responsibilities” for a job description. |
| Baseline / initial inventory | “Found on the first check”. Never imply these jobs were newly advertised. |
| Reassessment result | “New match after an updated check”. Do not say the job itself is new. |
| Mock / synthetic result | “Sample result” with the feature-specific warning in RF-02. |
| Provider | “AI service” in everyday help. Keep “OpenRouter” in consent and billing where the actual recipient/account matters. |
| Retention / purge | “Storage” / “Delete”. Explain exactly what is deleted. |
| Cooldown | “Waiting before trying again”, adding a real retry time when available. |
| Idempotency key / generation ID / protocol / schema | Never primary user-facing text. Put necessary diagnostic references in “Technical details”. |

Use **job** for a vacancy and **role** for a position in someone's work history. Use **daily summary** consistently instead of alternating between digest, batch and notification summary.

<a id="rf-02"></a>

## RF-02 · P2 · Remove preview branding and simplify sign-in

**Locations:** [app.tsx](frontend/src/app/app.tsx), `Shell` and `App`; [login.tsx](frontend/src/features/auth/login.tsx); [error-boundary.tsx](frontend/src/components/error-boundary.tsx).

| Current text / element | Replacement |
| --- | --- |
| Header “Personal workspace” | Remove. The app name and navigation already identify the space. |
| Unconditional “Development preview” badge | Remove. Do not replace it with an unconditional “Live”, “Ready” or “Secure” badge. |
| “Opening your workspace…” | “Opening Job Finder…” |
| “Cannot open your workspace” | “Job Finder couldn’t open” |
| Login heading “A little closer to your next role.” | “Sign in to Job Finder” |
| “Sign in to your private workspace.” | “See jobs from the companies you follow.” |
| “Access is managed by the owner of this installation.” | “Need help signing in? Ask the person who set up Job Finder.” |
| Login footer “Your companies. Your preferences. A wider view.” | Remove. |
| “This page could not load” | “This page couldn’t load” |
| “Your saved data has not been changed. Reload to try again.” | “Reload the page to try again. Unsaved changes on this page may be lost.” |
| “Reload page” | Keep. |

The error boundary cannot know whether an earlier write succeeded, so remove the unsupported claim that saved data did not change.

**Behaviour: preserve real test-mode warnings at the affected feature.** Removing preview branding must not disguise sample results as real AI analysis. AI, web search and notifications have separate modes; do not derive all three from `integration_mode`.

| Actual condition | Exact warning |
| --- | --- |
| CV AI analysis uses mock responses | “Sample analysis is enabled. The result is for testing and may not reflect your CV. No CV text is sent to an AI service.” |
| A job result has `integration_mode=mock` | “Sample match result — not a real assessment of this job.” |
| Web search is in mock mode | “Automatic website search is off for testing. Add the company’s website to continue.” |
| Notifications are in mock mode | “Notification sending is off for testing. No message will be sent.” |
| Mode/status lookup fails | “We couldn’t check whether this feature is ready.” Never default to an apparent live/ready state. |

<a id="rf-03"></a>

## RF-03 · P1 · Give first use and empty lists one clear next step

**Locations:** [jobs.tsx](frontend/src/features/inventory/jobs.tsx), `JobsPage`/`JobList`; [profile/page.tsx](frontend/src/features/profile/page.tsx); [companies.tsx](frontend/src/features/inventory/companies.tsx). **Behaviour required:** distinguish the states below. `matching_unavailable` currently combines missing profile and missing AI configuration; inspect the relevant state or extend the response instead of guessing.

Replace the Jobs introduction with **“Find jobs from the companies you follow.”** Under Shortlist, add **“Jobs that may fit your experience and preferences, including options worth exploring.”** Under All jobs, replace the existing collected/source disclaimer with **“All jobs found from the companies you follow, whether or not they match your preferences. Some company websites may have jobs we haven’t found.”**

Use this state order: initial request failure → missing Shortlist prerequisites → active filters with zero results → no companies → first check pending → failed/incomplete checks → successful empty result. Do not show the final empty-state claim while an earlier condition applies.

| Condition | Heading | Exact body | Action |
| --- | --- | --- | --- |
| No saved profile, Shortlist selected | “Create your job profile” | “Upload your CV and tell us what you want next. You can browse all jobs before setting up your shortlist.” | Primary “Set up profile” → `/profile`; secondary “Browse all jobs” → same list with `view=all`. |
| Profile exists, matching model missing | “Job matching needs setup” | “Your profile is ready, but AI matching hasn’t been set up. You can still browse all jobs.” | “Open AI settings” → Settings AI section; “Browse all jobs”. |
| Matching readiness could not be determined | “We couldn’t check your shortlist setup” | “Try again, or browse all jobs while matching is unavailable.” | “Try again”; “Browse all jobs”. |
| User-applied filters/search produce zero results | “No jobs match these filters” | “Try different keywords or clear your filters.” | “Clear filters”. Keep the company scope on a company page. |
| No companies followed | “Choose your first company” | “Add a company you’d like to work for. We’ll look for its job pages.” | “Follow a company” → `/companies`, focus company-name field. |
| First job check queued/running, zero jobs | “Looking for jobs” | “The first check hasn’t finished yet. You can leave this page and come back later.” | “View company checks” → `/companies`. |
| Zero jobs and one or more failed/incomplete checks | “Some job pages couldn’t be checked” | “There may be jobs we haven’t found. Check the company status for details.” | “View company checks”. |
| Shortlist empty, known match checks pending | “Your shortlist is being prepared” | “We’re checking the jobs found against your profile. You can browse all jobs while you wait.” | “Browse all jobs”. |
| Shortlist empty, match checks failed | “We couldn’t finish checking your matches” | “Browse all jobs, or review the problem in matching settings.” | “Browse all jobs”; “Open AI settings”. |
| Shortlist empty, completed available results | “No matches found yet” | “You can explore all jobs or adjust what you’re looking for in your profile.” | “Browse all jobs”; “Edit preferences” → `/profile` preferences. |
| All jobs empty, latest applicable checks completed | “No jobs found on the pages checked” | “We’ll check again on the company’s schedule. You can also visit its careers website.” | “View companies”; only show a website link when a verified URL exists. |

Never use the current omnibus paragraph beginning **“Check filters, company sources and assessment status…”**. It combines several unrelated causes and leaves the user to diagnose the system. Remove “View company watches”; use “View companies”. Implement the section focus/anchors required by these links; a link that merely opens the top of a long Settings page is insufficient.

<a id="rf-04"></a>

## RF-04 · P1 · Make job filters and badges understandable and truthful

**Locations:** [jobs.tsx](frontend/src/features/inventory/jobs.tsx), [assessment-label.ts](frontend/src/features/inventory/assessment-label.ts), [inventory/data.ts](frontend/src/features/inventory/data.ts).

| Current text / value | Replacement |
| --- | --- |
| “Search collected jobs” | “Search jobs” |
| Empty search placeholder | “Job title, skill or keyword…” |
| “Availability” | “Job status” |
| `open`: “Active or unknown” | “Open or not confirmed” |
| `active`: “Active only” | “Open” |
| `unknown`: “Unknown” | “Status not confirmed” |
| `closed`: “Closed” | “Closed” |
| `all`: “All statuses” | “Any status” |
| Raw job availability `active` / `unknown` / `closed` | “Open” / “Status not confirmed” / “Closed” |
| “First seen {date}” | “Found {date}” |
| “Initial inventory” | “Found on the first check” |
| Persistent “New listing” badge for all non-baseline jobs | Remove. The stored non-baseline flag does not establish recentness. Keep the “Found {date}” timestamp. |
| “Refresh jobs” | “Refresh list” |
| “Load more jobs” while loading | “Loading more jobs…”; retain “Load more jobs” when idle. |
| “Original listing ↗” | “View original listing ↗” |
| “Application page ↗” | “Go to application page ↗” |
| “Advertised publication” | “Posted by the company” |
| “Last seen” | “Last found on the company’s job page” |
| “{n} recorded content versions” | Remove from normal listing history; technical details may say “Saved versions: {n}”. |
| Raw adapter name in listing history | “Job website: {providerLabel}”; map `generic_http` → “Company website”, `greenhouse` → “Greenhouse”, `lever` → “Lever”, `ashby` → “Ashby”. |

Add job-status help: **“‘Open’ means the job was available when last checked. Check the original listing before applying.”** Keep this by the filter or in an accessible help disclosure, not repeated on every row. The application does not submit applications; do not label its external link “Apply now” in a way that implies an in-app submission.

In job detail, use **“Work arrangement”** instead of “Workplace”, and **“Employment type”** instead of “Employment”. For recognised source values, map `remote` → “Remote”, `hybrid` → “Hybrid”, `onsite`/`on-site` → “On-site”, `full_time`/`FullTime` → “Full-time”, `part_time`/`PartTime` → “Part-time”, `contract` → “Contract”, `internship` → “Internship”, `temporary` → “Temporary”. Match these known values case-insensitively; preserve other employer-supplied text rather than guessing its meaning.

Match labels must use the following explicit map, including cancelled and unfamiliar states:

| State | Label |
| --- | --- |
| `match` | “Relevant” |
| `possible_match` | “Worth a look” |
| `not_match` | “Not a match” |
| no result, `queued` | “Waiting for match check” |
| no result, `running` | “Checking match…” |
| no result, `blocked` | “Match check paused” |
| no result, `failed` | “Couldn’t check match” |
| no result, `cancelled` | “Match check cancelled” |
| no result and no operation | “Not checked for a match yet” |
| stale result | Prefix the applicable current status with “Match needs updating · ”. |
| unrecognised state | “Match status unavailable”. Never print the enum. |

Use “Worth a look” consistently wherever `possible_match` is displayed, including summaries. This is a label change only; the category stays in the shortlist. Explain both categories once: **“Relevant: a fit worth considering. Worth a look: some overlap, with gaps or details to check.”**

**Dates:** replace the universal null value “Not yet” with context-specific text: last check → “Not checked yet”; publication date → “Not provided”; next check without a known time → “Not scheduled”; unknown job observation date → “Not recorded”. Show readable local dates, for example `12 Oct 2026, 19:00`, without seconds. Use the configured summary timezone for notification times and show its readable label. Do not infer a future retry time.

<a id="rf-05"></a>

## RF-05 · P1 · Rewrite the actual match explanations, including backend output

**Locations:** [assessment.tsx](frontend/src/features/inventory/assessment.tsx), `AssessmentPanel`/`Evidence`/`FeedbackPanel`; [ai/matching.py](backend/app/ai/matching.py), `PROMPT` and Decisions conversion around lines 515–540.

| Current text | Replacement |
| --- | --- |
| “Assessment” | “How this job fits” |
| “Primary function: {value} · {relation}” | “Main responsibilities: {value}” and a separate mapped relation sentence below. When `value` is an extracted duties passage, display it as a quotation, not an invented job-family title. |
| `aligned` | “This work fits the types of jobs you’re looking for.” |
| `adjacent` | “This is related work where some of your experience may transfer.” |
| `unrelated` | “The main work differs from the types of jobs you’re looking for.” |
| `unclear` | “The listing doesn’t give enough detail to compare the main responsibilities.” |
| “Broad relevance: {n}/100.” | Move behind “More about this match”; label “Match guide: {n} out of 100”. |
| “This is a guide for review, not a hiring probability.” | “This is a rough guide to fit, not your chance of getting the job.” |
| “Relevance is uncertain.” | “There isn’t enough information to judge the fit.” |
| “Important details are unknown. Review the gaps before deciding.” | “Some important details are missing. Check the points below before deciding.” |
| “Transferable experience” | “Experience you could bring” |
| “Gaps and unknowns” | “What to check” |
| “Supporting evidence” | “See supporting details” |
| Evidence label “Reviewed profile” | “Your profile” |
| “Your criteria” | “Your preferences” |
| Criterion `met` / `not_met` / `unknown` | “Matches your preference” / “Doesn’t match your preference” / “Not enough information” |
| “How this was assessed” | “More about this match” |
| “Assessed {date} against your saved profile and preferences.” | “Checked {date} using your saved profile and preferences.” |
| “Domain evidence: met/not met/unknown.” | With focus mode, map `met` → “Industry preference: matched.”; `not_met` → “Industry preference: not matched.”; `unknown` → “Industry preference: not enough information.” With open/expand mode: omit this outcome; no required industry restriction was applied. Read the mode from the assessment's pinned profile revision. |
| “Primary duties and role fit” | “Responsibilities used for this check” |
| “Relevance evidence” | “Details used for the match guide” |
| Stale-result explanatory sentence | “This job, your profile or your matching settings have changed. Check the match again for an updated result.” |
| No-result explanatory sentence | “This job hasn’t been checked against your current profile. You can still read the listing and apply.” |
| “Review profile” / “Matching settings” | “View your profile” / “Open AI settings” |
| “Assess with current preferences” | “Check match” |
| “Requesting assessment…” / “Assessment in progress” | “Starting match check…” / “Checking match…” |
| “Assessment requested.” | “Match check requested. The result will appear here when it’s ready.” |
| Feedback help | “Keep a note of what you think about this job. Your feedback won’t change your shortlist or preferences.” |
| Feedback “Reason (optional)” | “Your notes (optional)” |
| “Discard edits and load saved feedback” | “Discard my changes and load saved feedback” |

**Backend replacements are mandatory.** A frontend-only edit leaves these current strings visible:

| Current generated explanation | Exact replacement rule |
| --- | --- |
| `Decisions outcome: met with selected listing support.` | “The listing matches your preference: {preferenceDescription}.” |
| `Decisions outcome: not_met with selected listing support.` | “The listing conflicts with your preference: {preferenceDescription}.” |
| `The listing does not show the outcome.` | “The listing doesn’t give enough information about your preference: {preferenceDescription}.” |
| `Listing terms for {criterion UUID} are not directly comparable (e.g. mismatched currency/period or eligibility).` | “We couldn’t reliably compare the listing with your preference: {preferenceDescription}. Check the original listing for details.” |

`preferenceDescription` must come from the **profile revision used for that assessment**, not the owner's newer profile. Add that presentation field or resolve the pinned revision on the backend. Never print a preference UUID. Do not select a specific salary/currency/eligibility explanation unless structured evidence establishes that cause.

The Decisions path currently leaves `reasons`, `transferable` and `gaps` empty. Do not add empty headings or fabricate narrative. Present the supported relation sentence, mapped preference results and original supporting details. If richer explanations are introduced later, they must remain evidence-backed.

**Structured evidence behaviour:** supporting quotes can currently contain serialized profile arrays or objects. Render recognised profile/preference structures as labelled lists using their original values; preserve the exact raw quotation under a nested “Original supporting text” disclosure when needed for audit. Never show JSON keys such as `origin`, `minimum_years`, `span_id` as ordinary prose. For aggregate experience, display “Estimated experience: {min}–{max} years” or “Estimated experience: at least {min} years” only from the actual evidence values; unknown bounds stay unknown.

Append this exact writing instruction to the existing chat matching prompt, without replacing its evidence and safety rules:

> Write user-visible reasons, gaps and explanations in plain English for someone looking for work. Address the user as “you”. State the practical connection or missing detail in one or two short sentences. Do not mention protocols, schemas, span IDs, policy versions or internal scoring machinery. Do not describe a match score as a chance of being hired. Keep uncertainty explicit. Keep supporting quotations exact and unchanged.

Apply the same plain-language requirement to the generated professional summary in [ai/profile.py](backend/app/ai/profile.py), while retaining its instruction not to invent facts or future preferences. Do not rewrite original job descriptions via AI merely to simplify the interface.

<a id="rf-06"></a>

## RF-06 · P2 · Make following a company a normal consumer task

**Locations:** [companies.tsx](frontend/src/features/inventory/companies.tsx), `CompaniesPage`, `Interval`, `CompanyEditor`, `CompanyPage`; [coverage.tsx](frontend/src/features/inventory/coverage.tsx).

| Current text | Replacement |
| --- | --- |
| “YOUR WATCHLIST” | Remove eyebrow. |
| Companies introduction | “Follow companies you’d like to work for. Browse the jobs we find, whether or not they match your profile.” |
| “Website or careers URL (optional)” | “Company website or careers page (optional)” |
| Website help, currently absent | “Paste the full address, starting with https://. If you don’t know it, leave this blank.” |
| “Check interval (hours)” | “How often should we check?” |
| “Edit company watch” | “Edit company” |
| “Pause monitoring” | “Pause job checks” |
| Pause help, currently absent | “Your company and jobs stay here. Scheduled checks stop until you turn this off and save.” |
| “Company watch saved.” | “Company settings saved.” |
| Company detail “Company watch saved” | “Following this company”. This does not claim checks have succeeded. |
| “Monitoring paused” | “Job checks paused” |
| “Check now” | “Check for jobs” |
| “Find job sources” | “Find job pages” |
| “All collected jobs” | “View all jobs” |
| “Collected jobs and coverage” | “Jobs found and latest checks” |
| “Job sources” | “Job pages” |
| “No source configured yet. Your company watch is retained.” | “We haven’t found a job page for this company yet. Add its website or choose ‘Find job pages’.” |
| “No companies followed yet. Add one above to start your watchlist.” | “You’re not following any companies yet. Add your first company above.” |

**Behaviour: replace the default hours field with a select.** Options: “Once a day” (`24`), “Twice a day” (`12`), “Every week” (`168`), “Custom”. Custom reveals “Hours between checks” with the current integer range 1–720 and help **“Choose 1 to 720 hours. This does not change your daily summary time.”** Preserve any existing custom value when opening the form. Display saved intervals with these same labels; other values use “Every {n} hours”.

**Important existing behaviour:** the company interval is a default for *new* job pages. It does not change existing page schedules. Do not call an existing-company edit a universal schedule change. In `CompanyEditor`, use **“Default schedule for new job pages”** above the selector and **“Existing job pages keep their own schedules. Change those under Job pages below.”** A future “Apply to all job pages” action would need backend implementation; this review does not assume it exists.

Replace `CompanyCoverage`'s repeated paragraphs with these exact lines, suppressing zero-count warnings:

| Condition / current line | Replacement |
| --- | --- |
| `{n} collected roles` | “{n} jobs found” (one: “1 job found”). |
| Active/unknown/closed breakdown | “{open} open · {unknown} status not confirmed · {closed} closed”. |
| Counts disclaimer | “These are jobs found on the pages we check. The company may have other vacancies.” |
| All sources disabled | “Checks are turned off for every job page. Previously found jobs are still available.” |
| Enabled-source count | “Checking {n} job pages”. One: “Checking 1 job page”. This means configured monitoring, not an assertion that a request is currently running. |
| Partial-source count > 0 | “We may be missing jobs from {n} pages.” One: “…1 page.” |
| Sources needing attention > 0 | “{n} job pages need attention. See the details below.” On company list use “Open this company for details.” |
| Sources without a successful check > 0 | “{n} job pages haven’t had a complete successful check yet.” |
| “Most recent successful source check” | “Most recent successful page check” |
| “Latest source attempt” | “Last check attempted” |
| “Next source check” | “Next job-page check” |
| “Next source discovery” | “Next search for job pages” |

Do not shorten the most-recent-page timestamp to “Company fully checked”; one page succeeding does not establish full coverage. Render company resolution explicitly: `unresolved` → “Job page not found yet”; `needs_review` → “Choose the right company website”; `sources_found` → “Job page found”; any other value → “Company status unavailable”. Retain the separate paused state.

<a id="rf-07"></a>

## RF-07 · P1 · Explain discovery failures without asking the user to configure infrastructure

**Location:** [discovery.tsx](frontend/src/features/inventory/discovery.tsx). Also apply the error mapping to the operation banner on company detail; two components must not describe the same failure differently.

| Current text | Replacement |
| --- | --- |
| “Source discovery” | “Job page search history” |
| Discovery introduction | “We look for this company’s careers page and job websites. If there’s more than one possible company, choose the right one below.” |
| “Loading discovery history…” | “Loading previous searches…” |
| “No discovery checks recorded yet.” | “No job-page searches yet.” |
| `{cursor} discovery steps checked.` | Remove from the default view. It is an internal traversal counter, not meaningful search progress. |
| “Open candidate page” | “Visit website” |
| “Search result · company identity unverified” | “Is this the right company? Open the website to check.” |
| “Verified job page · monitoring source saved” | “Job page found. A job check has been requested.” |
| “Possible job page · employer evidence needs review” | “Possible job page. We couldn’t confirm that its jobs belong to this company.” |
| “This updates the watched website and starts a new source check.” | “We’ll save this as the company website and look for its job pages.” |
| “Confirm company page” | “Use this company website” |
| Confirmation success | “Company website saved. A new search for job pages has been requested.” |
| “Older discovery checks” | “Show older searches” |
| “No company candidates to review from this check.” | “This search found no company websites to choose from.” |

Keep the confirmation checkbox **“I checked that the selected page belongs to {company}”**. A familiar-looking search title is not enough to confirm identity.

| Issue code | Exact user-facing message |
| --- | --- |
| `search_mock_mode` | “Automatic website search is off for testing. Add the company’s website to continue.” |
| `search_unconfigured` | “Automatic website search hasn’t been set up. Add the company’s website yourself, or ask the person who set up Job Finder for help.” |
| `search_budget` | “The website-search limit has been reached. You can still add the company’s website yourself.” |
| `search_rate_limited` | “The search service is busy. We need to wait before searching again.” |
| `search_cooldown` | “Waiting before searching again.” Add “Next search: {time}” only when a real next attempt is scheduled. |
| `search_candidates_unverified` | “Choose the website that belongs to the company you want to follow.” |
| `search_outcome_unknown` | “We couldn’t confirm the search result. Add the company’s website to continue.” Put the consumed search allowance in technical details, not the primary recovery sentence. |
| `generic_collection_pending`, `adapter_unavailable` | “Job Finder can’t read this job page yet. You can still visit it to browse jobs.” |
| `discovery_page_limit`, `discovery_candidate_limit` | “We reached the limit for this search. There may be job pages we haven’t found.” |
| `fetcher_unavailable`, `fetcher_configuration` | “Automatic job checks haven’t been set up. Ask the person who set up Job Finder for help. Previously found jobs are still available.” |
| `isolation_unverified`, `isolation_not_verified` | “Automatic job checks are paused until setup checks are complete. Ask the person who set up Job Finder for help.” |
| `robots_denied` | “This website doesn’t allow automatic checks. Visit it directly to browse jobs.” |
| `robots_unavailable` | “We couldn’t check this website’s access rules. Its job check will need to wait.” |
| `unverified_redirect`, `generic_redirect_unverified` | “This page moved to a different website. Confirm the company’s website before checking again.” |
| `discovery_step_interrupted` | “The search stopped before it finished. Try ‘Find job pages’ again.” |
| `discovery_content_type`, `discovery_http_error`, `ats_response_unverified` | “We couldn’t read jobs from this page. Visit the website or try another job page.” |
| Unrecognised discovery issue | “We couldn’t finish this search. You can try again or add the company’s website yourself.” |

Render the known next action beside the message: **“Edit company website”**, **“Find job pages”** or **“Visit job page”**, as appropriate. Do not render a website action if its URL has not passed the existing safe-link checks. Setup-only failures get the help explanation, not a retry button that cannot fix them.

Action assignment is explicit: mock/unconfigured/budget/unknown-search outcomes and unverified redirects → **“Edit company website”**; unverified search candidates → focus the existing website choices; interrupted/limited discovery → **“Find job pages”** after any enforced wait; unsupported reading, denied automatic access and unreadable pages → **“Visit job page”** when a safe URL exists; fetcher/isolation setup failures → **“View technical setup”**. Rate-limit/cooldown states get the real next-attempt time, not an immediate retry button.

<a id="rf-08"></a>

## RF-08 · P2 · Keep technical job-page tools available but out of the everyday path

**Locations:** [companies.tsx](frontend/src/features/inventory/companies.tsx), `SourceCard` and manual-board form; [source-rules.tsx](frontend/src/features/inventory/source-rules.tsx).

| Current text | Replacement |
| --- | --- |
| `{adapter} source` | “{providerLabel} job page”, using RF-04's provider map. |
| “Partial site coverage. Missing listings alone will not close roles.” | “We may not find every job on this website. A job won’t be marked closed just because it was missing from one check.” |
| “Open source” | “Visit job page” |
| “Monitoring enabled” / “Monitoring disabled” | “Automatic checks on” / “Automatic checks off” |
| “Source checks paused with this company.” | “Job checks are paused for this company.” |
| “No scheduled check while this source is disabled.” | “Turn on automatic checks to check this page again.” |
| “Source settings and recent checks” | “Check schedule and history” |
| “Enable this source” | “Check this job page automatically” |
| “Save source” / “Source settings saved.” | “Save page settings” / “Job-page settings saved.” |
| Raw run state | `collecting` → “Checking…”; `complete` → “Check complete”; `partial` → “Some jobs may be missing”; `failed` → “Check failed”; `cancelled` → “Check cancelled”; `expired` → “Check stopped before finishing”; unknown → “Check status unavailable”. |
| Raw comma-separated run issues | Use RF-07/RF-17 mappings. Never turn underscores into spaces and present the result as explanatory text. |

**Behaviour: move “Add a known job board” behind a collapsed “Add a job page manually” section.** Place it after ordinary company/job controls. Intro: **“Use this if you know the company’s Greenhouse, Lever or Ashby job page.”** Keep its current supported providers; do not imply any URL is accepted.

| Manual-board field | Exact replacement |
| --- | --- |
| “Job board provider” | “Job website” |
| “Board identifier” | “Company name in the job-page address” |
| Identifier help | “Enter only the company part of the address. For jobs.lever.co/example, enter example.” |
| “Lever region” | “Lever website address” |
| `global` / `eu` labels | “jobs.lever.co” / “jobs.eu.lever.co” |
| Identity checkbox | “I checked that this job page belongs to {company}.” |
| “Add source” | “Add job page” |
| Success | “Job page added. Its jobs will appear after a successful check.” |

A paste-the-full-link control would be a further behaviour change; do not simply relabel the existing identifier input “URL”. It does not currently accept one.

**Extraction rules stay technical.** Renaming CSS selectors to something friendly does not make writing them a nontechnical task. Put the editor behind **“Technical setup” → “Website reading rules”**, collapsed by default. Display **“These settings need website-development knowledge. Leave automatic reading on unless someone is helping you fix this job page.”**

| Current text | Replacement |
| --- | --- |
| “Extraction method” | “How Job Finder reads this page” |
| “Use custom extraction rules” | “Use custom website rules” |
| Automatic explanation | “Job Finder reads this page automatically. Save to remove any custom rules.” |
| “Job cards” | “Repeated job item — CSS selector” |
| Other selector labels | Append “— CSS selector” to Job title, Job detail link, Job description, Employer name, Location, Next-page link, No-vacancies message, Closed-job marker and Closing date. Keep optional markers. |
| “Optional fields and pagination” | “Optional fields and next-page rules” |
| “Closing dates must be ISO dates.” | “Closing dates must use YYYY-MM-DD, for example 2026-10-12.” Preserve the separate existing limitations. |
| “Employer scope” / raw `card` or `page` | “Where to find the employer name” / “Each job item” or “The whole page”. |
| “Saved revision {n}” | “Current saved rules” |
| “Compare saved rules” | “Compare with saved rules” |
| “Keep my draft for review” | “Keep my changes” |
| Keeping-draft explanation | “Your changes will replace the saved rules only when you choose ‘Save website rules’.” |
| “{n} verified jobs found in the saved page from {date}.” | “{n} jobs recognised in the saved page from {date}.” One: “1 job recognised…”. This is not a guarantee that a vacancy is still open. |
| Parsed-success sentence | “This saved page was read successfully. Other jobs may exist on the website.” |
| Incomplete preview sentence | “Some jobs on this saved page could not be read. Review the details below.” |
| “Preview saved page” / “Previewing…” | “Test rules on saved page” / “Testing rules…” |
| “Save extraction rules” | “Save website rules” |
| Success | “Website rules saved. They’ll be used the next time this page is checked.” |
| Preview help | “This test uses a previously saved page. It won’t visit the website or use AI. If no saved page is available, choose ‘Check for jobs’ first. Some websites don’t allow a page to be saved for reuse.” |

Do not remove precise selector syntax help from this technical section. Hide complexity from normal journeys; preserve the detail needed by someone deliberately troubleshooting it.

<a id="rf-09"></a>

## RF-09 · P1 · Make CV upload and privacy understandable before consent

**Locations:** [profile/page.tsx](frontend/src/features/profile/page.tsx), `UploadCv`/`DraftReview`; [documents/parser.py](backend/app/documents/parser.py); [services/profiles.py](backend/app/services/profiles.py).

| Current text / placement | Exact replacement |
| --- | --- |
| “YOUR DIRECTION” | Remove eyebrow. |
| Profile introduction | “Review your experience and tell us what you want from your next job.” |
| “Start with your CV”, no saved profile | “Upload your CV” |
| Same heading when a profile exists | “Update your CV” |
| Upload introduction | “Upload a PDF, Word (.docx) or text (.txt) file under 10 MB. PDFs can have up to 50 pages. You’ll review the details before we use them to find matches.” |
| Additional format help | “For PDFs, use a file where you can select and copy the text. Scanned images aren’t supported.” |
| Existing-profile upload help | “Your current profile stays in use until you review and save the new one. Your job preferences will be kept for you to review.” |
| “Original files are parsed locally…” paragraph | “Your CV is read on the Job Finder server. For AI analysis, text from your CV is sent to OpenRouter and the AI service it selects. We try to remove contact details, but the text may still identify you.” |
| Consent checkbox | “I agree to share text from my CV with OpenRouter and its selected AI service for analysis.” |
| “Keep my original CV after approval” | “Keep the uploaded CV and its extracted text until I delete them” |
| Retention helper | “If you leave this unchecked, the uploaded file and extracted text are scheduled for deletion 30 days after you save the reviewed profile. Your saved profile and supporting details remain until you delete your profile. CVs awaiting review are kept.” |
| Privacy link, currently absent at upload | “Manage stored CVs and profile data” → the storage section on this page; expand it and move focus to its heading. |
| “Upload and analyse” | “Create profile from CV” on first upload; “Create updated profile” on replacement. |
| File missing | “Choose a PDF, Word (.docx) or text (.txt) file.” |
| File too large / `document_too_large` | “This file is too large. Choose a smaller CV under 10 MB.” |
| “Your CV needs attention” on any failed/blocked operation | “We couldn’t prepare your profile”. Follow with the actual task-specific explanation. A service/setup failure is not a defect in the user's CV. |
| “Waiting for processing. You can leave this page and return later.” | “Waiting to read your CV. You can leave this page and come back later.” |
| “Retry processing” | “Try reading this CV again”, only when retry can address the cause. |
| “CV drafts” | “CVs to review” |
| Draft `processing` / `failed` / `blocked` / `cancelled` | “Preparing your profile…” / “Couldn’t prepare profile” / “Profile preparation paused” / “Profile preparation cancelled”. |
| “Open draft” | For review-ready drafts: “Review profile”. For other states: “View progress” or “View problem” for failed/blocked. |

**File-size decision:** keep the existing enforcement threshold of 10 × 1024 × 1024 bytes. “Under 10 MB” is a conservative, familiar instruction: every file under decimal 10 MB meets that size limit. Do not change the backend limit merely to edit copy, and do not display “MiB” in the basic upload journey.

**Consent behaviour:** load the real AI mode before enabling upload. While status is loading, show **“Checking analysis settings…”**. On failure show **“We couldn’t check the analysis settings. Try again before uploading your CV.”** with **“Try again”**. Do not treat an unknown status as consent-ready live mode or as safe sample mode. Use RF-02's sample-analysis warning instead of the live consent block when mock mode is positively known.

Parser messages must change at their origin or be mapped to typed error reasons before display:

The API's `unsupported_document` and operation's `invalid_document` currently carry parser prose. Add a stable document-reason field if the mapping is done on the client; do not use string matching against exception text as the long-term interface contract. Unclassified `invalid_document` uses the final unreadable-file fallback below.

| Current parser message / condition | Replacement |
| --- | --- |
| “Use a text PDF, DOCX, or UTF-8 text file.” | “Choose a PDF with selectable text, a Word (.docx) file or a plain-text (.txt) file.” |
| Invalid text / decode failure | “We couldn’t read this text file. Save it as UTF-8 text, or upload a Word (.docx) file.” Keep UTF-8 only in this format-specific recovery instruction. |
| “Upload an unencrypted PDF.” | “This PDF is password-protected. Upload a copy without password protection.” |
| PDF over 50 pages | “This PDF has more than 50 pages. Upload a shorter version.” |
| Expanded DOCX safety limit / excessive nested tables | “This Word file is too complex to read. Try a simpler copy or a PDF with selectable text.” |
| “The archive is not a DOCX document.” | “This isn’t a supported Word document. Save it as a .docx file and upload it again.” |
| Macro-enabled document | “This Word file contains macros. Upload a copy without macros, or use a PDF with selectable text.” |
| Extracted text too large | “This CV contains too much text to read in full. Upload a shorter version.” |
| No readable text / “OCR is not supported” | “We couldn’t find readable text in this file. If it’s a scan or photo, export a text-based PDF or Word document instead.” |
| `parser_timeout`, `parser_failed`, otherwise unreadable | “We couldn’t read this CV. Try a simpler PDF with selectable text, or a Word (.docx) file.” |
| `empty_document` | “This file is empty. Choose another CV.” |

Do not automatically keep asking for another CV when the cause is missing AI configuration, a spending limit or a service outage. Those messages and actions come from RF-17.

<a id="rf-10"></a>

## RF-10 · P2 · Express profile preferences in the language of a job search

**Locations:** [profile/editor.tsx](frontend/src/features/profile/editor.tsx), schema messages, `fieldLabels`, Experience/Preferences fields and `describe`; [profile/page.tsx](frontend/src/features/profile/page.tsx), saved summary.

| Current text | Replacement |
| --- | --- |
| “Your reviewed profile” | “Your profile” |
| “Experience” section | “Your experience” |
| “Preferences” section | “What you want next” |
| “Desired roles” / “Desired roles or functions — one per line” | “Jobs you’re interested in”; help “Add one job title or type of work per line.” |
| Summary validation “Add a reviewed professional summary.” | “Add a short summary of your experience.” |
| Desired-role validation | “Add at least one job title or type of work you’re interested in.” |
| “Role title” in work history | “Job title” |
| Start-date help “Use YYYY, YYYY-MM, or YYYY-MM-DD.” | “Enter a year, month or full date: 2020, 2020-03 or 2020-03-15. Leave it blank if you’re unsure.” |
| End-date help | “Use the same date format as the start date. Leave it blank if you’re unsure, or select ‘I currently work here’.” |
| “Responsibilities — one per line” | “Main responsibilities”; help “Add one responsibility per line.” |
| Skills/industries/qualifications/languages “— one per line” labels | “Skills”, “Industries you’ve worked in”, “Qualifications”, “Languages”. Add “Add one item per line.” as associated help. |
| “Experience is calculated from the union of dated roles…” | “We estimate your experience from the dates in your work history. Overlapping jobs count only once. Missing dates make the estimate less certain.” |
| “Your own years-of-experience estimate (optional)” | “Your estimate of total years of experience (optional)” |
| Override help | “Leave this blank to use the estimate from your work history.” |
| Saved-profile “Not enough dated information” | “Add work dates to estimate your experience.” |
| “Which domains would you like to explore?” | “Which industries or fields interest you?” |
| “Open to any domain” | “Open to any industry or field” |
| Open help | “Include jobs where your experience could transfer, even in a new industry.” |
| “Prefer selected domains, explore others” | “Prefer some industries, but stay open to others” |
| Expand help | “Name your preferred industries or fields. Other jobs can still appear in your shortlist.” |
| “Focus on selected domains” | “Focus on selected industries or fields” |
| Focus help | “Exclude jobs known to be outside your choices. Jobs with an unclear industry can still appear for you to review.” |
| “Selected domains — one per line” | “Industries or fields you want to explore”; help “Add one per line.” |
| Domain validation | “Add an industry or field, or choose ‘Open to any industry or field’.” |
| Saved summary “Domains” | “Industries and fields” |
| “Location, seniority and other criteria” | “Location, pay and other preferences” |
| Criteria introduction | “Mark a preference ‘Must have’ only if you would rule out a job that clearly doesn’t meet it. Jobs with missing details can still appear for you to check.” |
| Preference type `capability` | “Skills and responsibilities” |
| `seniority` | “Experience level” |
| `employment` | “Employment type” |
| `location` | “Location” |
| `remote` | “Remote or hybrid work” |
| `compensation` | “Pay” |
| `other` | “Other” |
| Importance `preferred` / `required` | “Nice to have” / “Must have” |
| Empty preference description | “Describe what you’re looking for.” |
| “Functions you want to exclude — one per line” | “Types of work you don’t want”; help “Add one per line. Leave this blank if you have no exclusions.” |
| “Broad shortlist threshold” | “How broad should your shortlist be? (advanced)” |
| Threshold help | “The default is 30. Lower values include more possibilities; higher values narrow the list. Jobs with clearly unrelated responsibilities or a known conflict with a ‘Must have’ preference are still excluded. This number is not your chance of getting a job.” |
| “Minimum relevance (0–100)” | “Minimum match guide score (0–100)” |
| Invalid threshold | “Enter a whole number from 0 to 100.” |
| “Extracted source text” | “Text read from your CV” |
| Parser/reading-order explanation | “Use this to check whether anything was missed. Columns and tables may appear in a different order from your original CV.” |

Do not hardcode example professions or industries into these fields. The user can be changing career or industry. A focus preference is not proof of prior industry experience.

Apply these labels to `fieldLabels` and the conflict formatter as well. Replace raw `open`/`expand`/`focus`, `required`/`preferred`, and criterion kinds inside comparison text with their exact presentation labels above. Unknown dates must render **“Date not provided”**, not `?`. For dynamic remove actions, visible **“Remove role”** / **“Remove preference”** is sufficient; accessible names must identify the row, for example **“Remove role: {title} at {employer}”** or **“Remove preference: {description}”**. Fall back to the row number only for blank entries.

<a id="rf-11"></a>

## RF-11 · P1 · Explain saving, draft approval and conflicting changes

**Locations:** [profile/editor.tsx](frontend/src/features/profile/editor.tsx), conflict/activation flow; [profile/page.tsx](frontend/src/features/profile/page.tsx); other settings conflict controls.

| Current text | Replacement |
| --- | --- |
| “Reviewed revision {n}. Changes create a new revision and queue matching updates.” | “Saved changes are used to update your matches. You can keep browsing jobs while this happens.” |
| “Approve profile” | “Save and use this profile” |
| “Save draft” | “Save for later” |
| Draft-save success | “Draft saved. It isn’t being used for matching yet.” |
| Active-profile-save success in both editor and page | “Profile saved. Your matches will update as jobs are checked.” |
| Before saving an active profile | “Saving updates the profile used for matching. Rechecking jobs may use your AI budget.” |
| “Back to saved profile” | “Cancel editing” with the unsaved-change behaviour below. |
| “Compare saved changes” | “Compare changes” |
| “Reconcile saved changes” | “Choose which changes to keep” |
| Conflict introduction mentioning revision/activation | “Your profile changed while you were editing. Compare the versions below and choose what to keep. You’ll review the result before saving it for matching.” |
| “Your edits” / “Saved profile” / “Saved draft” | “Your changes on this page” / “Currently saved profile” / “Currently saved draft” |
| Each field's choice label | “Keep my changes” / “Use the saved profile value” / “Use the saved draft value”. Group under the field's readable legend; do not concatenate awkward field names. |
| No active-profile notice | “There is no saved profile in use. You can review these details and save them as your profile.” |
| Copied-profile-facts notice | “Details copied from your saved profile will be treated as corrections you’ve confirmed.” |
| “Continue with these choices” | “Review combined profile” |
| “Refresh comparison” | “Load the latest saved versions” |
| Post-comparison message | “Your combined profile is ready to review. It won’t be used for matching until you save it.” |
| “Compare with profile revision {n}” | “Compare with your saved profile” |
| Replacement-CV comparison introduction | “Review the details from your new CV. Your saved job preferences are still here. Use the comparison below to keep details from your current profile.” |
| “Your values already agree with the saved versions.” | “There are no differences to resolve.” |
| “Your edits and choices are preserved.” | “Your changes and choices are still on this page.” Only append while that mounted draft is actually retained. |

Keep the reviewed-experience confirmation **“I have reviewed my experience and preferences.”** It confirms the user's action; it does not certify model accuracy.

**Behaviour: make “Save for later” genuinely save incomplete preferences.** The current editor uses the same completion validator for saving a draft and activating it, so an empty desired-role field prevents even a draft save. Separate draft validity from activation readiness: allow an empty summary, desired-role list or industry choice in a saved draft, and require them only for “Save and use this profile”. Retain type, size and security constraints. A newly added preference row still needs its description or must be explicitly removed; do not silently drop user input. Draft save does not require the review checkbox and does not trigger matching. Verify the draft API continues to accept the incomplete-but-valid draft contract.

**Behaviour: add a consistent unsaved-change confirmation** to Profile, AI settings, notification schedule, company/page editors and feedback before navigation or discard. The prior browser review established actual profile edit loss; reassuring copy alone cannot fix it.

- Heading: **“Discard your unsaved changes?”**
- Body: **“Changes you haven’t saved on this page will be lost.”**
- Primary safe action: **“Keep editing”**.
- Destructive action: **“Discard changes”**.
- Successful save clears the dirty state. A clean form navigates without this dialog. Preserve the existing explicit conflict choices; never silently overwrite a newer saved version.
- For “Use saved rules/settings/feedback”, show this confirmation when it discards dirty local input. Its body is **“Your changes will be replaced with the saved version.”**

Do not use “Reload the page” as the primary conflict-recovery instruction. It destroys exactly the input that the user is trying to save. Where a comparison does not yet exist, say **“These settings changed while you were editing. Your changes haven’t been saved. Review the saved settings before trying again.”** and provide the intentional, confirmed load action.

<a id="rf-12"></a>

## RF-12 · P1 · Name the exact consequences of data deletion

**Location:** [profile/data.tsx](frontend/src/features/profile/data.tsx). Keep privacy controls accessible but collapsed away from routine profile review.

| Current text | Replacement |
| --- | --- |
| “CV storage and profile data” | “Stored CVs and privacy” |
| Storage introduction | “Uploaded CV files and extracted text are scheduled for deletion 30 days after you save the reviewed profile, unless you choose to keep them. CVs awaiting review are kept. Your saved profile and supporting details remain until you delete your profile.” |
| “No CV documents stored.” | “No uploaded CVs are listed.” The list can include records whose files were already deleted; this is a zero-record message only. |
| “Original file and raw text removed.” | “The uploaded file and extracted text have been deleted.” |
| “Approved” / “Not yet approved” | “Reviewed and saved” / “Not yet saved as your profile” |
| “Keep this original until I delete it” | “Keep this CV file and its extracted text until I delete them” |
| “Download original” | “Download CV” |
| “Remove original” | “Delete uploaded CV” |
| File-deletion confirmation heading | “Delete this uploaded CV?” |
| File-deletion confirmation body | “This deletes the uploaded file and its extracted text. Your saved profile and any existing draft details remain. If this CV is still being analysed, that analysis will stop. Information already sent to an AI service cannot be recalled.” |
| “Confirm removal” / “Keep original” | “Delete uploaded CV” / “Keep CV” |
| File-deletion success, currently absent | “Uploaded CV and extracted text deleted.” Show only after the deletion request succeeds. |
| Storage-checkbox success, currently absent | Checked: “This CV will be kept until you delete it.” Unchecked with approval: “This CV is scheduled for deletion 30 days after it was reviewed and saved.” Unchecked without approval: “This CV will be kept until you review it, then scheduled for deletion after 30 days.” |
| “Delete profile and all CV data” | “Delete profile and CV data” |
| Full-deletion body | “This deletes your profile, earlier profile versions, CV drafts, uploaded files, job-match explanations, feedback notes and saved summary contents from Job Finder. Your followed companies and job listings remain. Existing backups are not changed. Billing records remain without CV content. Information already sent to an AI service or notification app is not recalled.” |
| Full-deletion irreversibility line | “You can’t undo this in the app.” |
| “Type DELETE PROFILE to confirm” | Keep exactly; the backend requires this phrase. |
| “Delete profile and CVs” | “Delete profile and CV data” |
| Full-deletion success | “Profile and CV data deleted from Job Finder. You can upload a new CV when you’re ready.” |

Do not claim data was deleted from backups, OpenRouter, routed AI providers or devices. Do not turn “scheduled for deletion” into a promise of exact instantaneous removal. Keep the confirmation scoped to the actual request; do not combine file-only deletion with full profile deletion.

<a id="rf-13"></a>

## RF-13 · P2 · Make Settings useful without presenting an administration console

**Locations:** [settings/page.tsx](frontend/src/features/settings/page.tsx), [ai.tsx](frontend/src/features/settings/ai.tsx), [billing.tsx](frontend/src/features/settings/billing.tsx), [notifications.tsx](frontend/src/features/settings/notifications.tsx).

Replace the Settings introduction **“Processing and workspace status.”** with **“Choose when to hear about jobs and manage matching, privacy and spending.”** Remove “YOUR WORKSPACE”.

Use this order and these exact section names:

1. **Daily summary** — notification schedule and device connection help.
2. **AI matching and analysis** — concise status for each of the three tasks; retain independent model selection under “Change AI models”.
3. **Spending limits** — user-controlled daily limits and current spend; visible without opening technical setup.
4. **Stored CVs and privacy** — a link labelled “Manage stored CVs and profile data” to Profile's existing storage controls; do not duplicate the deletion form.
5. **Technical setup** — collapsed; connection configuration details, advanced model parameters and troubleshooting references. Intro: **“These settings are for the person who set up Job Finder. Most people won’t need to change them.”**

**Behaviour:** introduce stable section anchors, for example `#notifications`, `#ai`, `#spending`, `#technical`. Navigation to an anchor must reveal and focus that section. Normal error actions go to the relevant section, not to a general wall of configuration fields.

Replace the existing Connection/Services summary as follows:

| Current | Replacement |
| --- | --- |
| “Connection” | “Setup status” |
| “Services” | “AI processing” |
| “Mock responses for development” | “Sample responses — AI processing is off” |
| “Live integrations” | “External AI requests enabled”. This is a mode, not proof of working AI, search or notifications. |
| Profile “Configured” / “Not configured” | “Profile saved” / “Profile not set up” |

Show search/notification readiness only from their own verified state. The current `/status` fields cannot support an “Everything is working” banner. When no device-receipt verification exists, never show “Phone connected” or “Notifications delivered”.

<a id="rf-14"></a>

## RF-14 · P1 · Explain AI choices and their costs honestly

**Location:** [settings/ai.tsx](frontend/src/features/settings/ai.tsx), `AiSettings`, `TaskForm`, `LimitsForm`. Also see engineering review ER-01/02/13: wording alone does not repair the live ledger or protocol configuration defects.

| Current text | Replacement |
| --- | --- |
| “AI models” | “AI matching and analysis” |
| “Choose a model independently for each task. Saving a choice does not make a paid request.” | “Job Finder uses AI to read your CV, understand job pages and check matches. You can choose a different model for each task. Changing the matching model can recheck existing jobs and use your AI budget.” |
| `profile_analysis`: “CV analysis” | “Reading your CV”; description “Creates a profile from your CV for you to review.” |
| `job_extraction`: “Job extraction” | “Reading job pages”; description “Finds job details on websites that don’t provide a ready-made job list.” |
| `job_matching`: “Job matching” | “Checking job matches”; description “Compares jobs with your saved experience and preferences.” |
| “OpenRouter key configured on the server.” | “An OpenRouter connection has been set up.” Do not label it tested until a successful check exists. |
| “OpenRouter key is not configured on the server.” | “AI processing hasn’t been connected. Ask the person who set up Job Finder to connect OpenRouter.” |
| Existing privacy notice after connection status | “AI analysis shares relevant CV, profile or job text with OpenRouter and its selected AI service. We request providers that don’t collect this data by default, but this does not make your information anonymous.” |
| `Revision {n} · {validation_state}` | Remove revision. Map `unvalidated` → “Not tested yet”, `validated` → “Model responded successfully”, `mock_only` → “Sample settings checked”, `blocked` → “Setup needs attention”; unknown → “Test status unavailable”. Normal inference also sets `validated`, so it must not be described exclusively as a dedicated test pass. |
| “Model ID” | “OpenRouter model name” |
| Model input helper | “Enter the exact model identifier from OpenRouter, in the form maker/model. Ask the person who set up Job Finder if you’re unsure.” |
| “Use only zero data retention endpoints” | “Require providers that offer zero data retention”; help “This requests providers that report they won’t retain request data. It can limit which models are available. It does not make your information anonymous.” |
| Task save buttons | “Save CV model”, “Save job-page model”, “Save matching model”. |
| Matching-save notice, before action | “Saving matching settings can recheck existing jobs and use your AI budget.” |
| General successful save | “AI settings saved.” |
| Matching successful save | “Matching settings saved. Existing jobs may be checked again using your AI budget.” |
| “Allow a synthetic validation request that may incur API cost” | “I agree to a connection test that may use my AI budget.” |
| “Validate saved model” | “Test saved model” |
| “Check mock configuration” | “Check sample settings” |
| Test help | “The test uses sample text, not your CV. It checks that the saved model can respond; it does not prove that its job matches are accurate.” |
| Disabled test because form is dirty | “Save your changes before testing this model.” |
| Disabled test because no model | “Choose and save a model before testing.” |
| Disabled test because consent missing | “Agree to the possible test cost to continue.” |
| “Validation queued.” | “Model test requested.” |
| “Synthetic validation passed. This does not verify matching quality.” | “The model responded successfully. This test does not check the quality of its job matches.” |
| “Mock configuration checked. No provider request was made.” | “Sample settings checked. No AI service was contacted.” |
| “A newer configuration is available. Your edits are preserved.” | “These settings changed while you were editing. Your changes are still on this page.” |
| “Replace edits with saved settings” | “Load saved settings”, with RF-11's discard confirmation. |

**Advanced settings:** keep configurable models as required by the product. Move the following fields into Technical setup, grouped by task; preserve exact numeric limits and supported protocol behaviour. Do not add an unverified “Recommended model” or silently choose one.

| Current advanced label | Exact replacement and help |
| --- | --- |
| “Fallback model IDs” | “Backup models (optional)”. Help: “Exact OpenRouter model identifiers, separated by commas. The same privacy rules apply.” |
| “Provider slugs” | “Allowed AI providers (optional)”. Help: “Exact provider identifiers from OpenRouter, separated by commas. Leave blank to use any provider that meets these settings.” |
| “Input token limit” | “Maximum input size (tokens)”. Help: “Tokens are units of text used by AI services. A low limit can prevent a whole CV or job description from being read.” |
| “Output token limit” | “Maximum response size (tokens)”. Help: “A low limit can cut off the AI response.” |
| “Timeout (seconds)” | “Maximum wait per request (seconds)” |
| “Temperature (optional)” | “Response variation (temperature, optional)”. Help: “Availability and effect depend on the selected model.” |
| “Reasoning effort” | “Reasoning setting”. Options: “Provider default”, “Low”, “Medium”, “High”. Help: “Supported by some models. It can affect cost and response time.” |
| Input/output price ceilings | “Maximum input price (US$ per million tokens)” / “Maximum response price (US$ per million tokens)” |
| “Request fee ceiling (USD)” | “Maximum fixed fee per request (US$)” |

Do not describe fields as effective if the selected protocol ignores them. Hide or disable unsupported fields with **“Not available for this model’s connection type.”** Protocol compatibility needs the engineering fix already documented; a copy change cannot substitute for it.

<a id="rf-15"></a>

## RF-15 · P1 · Turn billing recovery into understandable spending information

**Locations:** [ai.tsx](frontend/src/features/settings/ai.tsx), `LimitsForm`/usage; [billing.tsx](frontend/src/features/settings/billing.tsx).

| Current text | Replacement |
| --- | --- |
| “Daily limits” | “Spending limits” |
| Daily-limit help | “Limits reset at 00:00 UTC each day. Automatic retries count towards them. Money reserved for an unconfirmed charge stays unavailable until the charge is checked.” |
| Reset-time addition | “Next reset: {localDateTime} ({timezoneLabel}).” Calculate the next UTC-midnight instant, then format it in the owner's selected timezone. Never move the budget reset to local midnight. |
| “Set a provider key spending limit as an additional safeguard.” | Move to Technical setup: “For extra protection, the person managing the OpenRouter account can set a spending limit there too.” |
| “Calls per day” | “Maximum AI requests per day” |
| “Estimated spend per day (USD)” | “Daily AI budget (US$)” |
| Budget help | “This limit uses estimated costs before requests are sent. Charges that haven’t been confirmed can temporarily reduce the available budget.” |
| “Usage today (UTC)” | “AI usage today”; associated help “The day runs from 00:00 to 23:59 UTC.” |
| “{n} calls · ${cost} recorded · ${held} held” | “{n} requests · US${cost} recorded · US${held} reserved”. Use “1 request” for one. |
| “Held amounts include unresolved requests from earlier days.” | “Reserved amounts may include earlier requests whose final charge is not yet confirmed. A reservation is not an extra charge.” |
| “This task is paused pending billing reconciliation.” | “This task is paused because a previous charge hasn’t been confirmed. Review it under ‘Charges to check’.” |
| “Request history and recovery” | “Charges to check” |
| No unresolved charges | “No charges need checking.” |
| “The charge is unresolved. Its reservation stays in the budget…” | “We don’t know the final charge for this request yet. Its reserved amount remains unavailable in your budget until the charge is confirmed.” |
| “Fetch provider charge” | “Check charge with OpenRouter” |
| “Generation: {id}” | “Request reference: {id}” inside “Technical details”, with an explicit copy-reference control if added. |
| No generation ID explanation | “We didn’t receive a request reference, so we can’t check the charge automatically. Ask the person managing the OpenRouter account to check it.” |
| “Provider lookup is disabled in mock mode.” | “Charge lookup is unavailable while sample responses are enabled.” |
| “Provider charge recorded.” | “Charge confirmed with OpenRouter.” Only when a charge was actually recorded, not merely because a no-op operation returned successfully. |
| “Record a charge you verified” | “Enter a charge checked in OpenRouter” |
| Manual entry help | “Check this exact request in OpenRouter’s billing records first. Enter 0 only if you confirmed there was no charge. This changes Job Finder’s spending record; it does not change your bill or repeat the AI request.” |
| “Verified cost (USD)” | “Confirmed charge (US$)” |
| “I checked this request in provider billing” | “I checked this exact request in OpenRouter’s billing records.” |
| “Record verified cost” | “Save confirmed charge” |
| Manual-recovery success | “Charge saved. The AI request has not been repeated. Return to the job or CV if you want to try it again.” |
| “Recent request accounting” | “Recent AI requests” |
| “No AI requests recorded.” | “No AI requests yet.” |
| `provider` / `owner_verified` / `rejected` / `legacy_reported` cost source | “Reported by OpenRouter” / “Confirmed by you” / “Rejected before processing” / “Earlier spending record”. |

Map raw billing states explicitly: `reserved` → “Request reserved”; `unknown` → “Charge not confirmed”; `completed` → “Response received”; `succeeded` → “Finished”; `invalid` → “Response couldn’t be used”; `failed` → “Request failed”; `reconciled` → “Charge confirmed with OpenRouter”; `owner_reconciled` → “Charge confirmed by you”; unfamiliar state → “Request status unavailable”. A failed/unusable response can still cost money: never infer “No charge” from the state alone.

**Formatting:** retain small amounts instead of rounding them to zero. Display 4 decimal places normally; for a positive value below US$0.0001 show “Less than US$0.0001”, with the full stored precision in details. This prevents “US$0.0000” from implying a free request.

**Behaviour prerequisite:** ER-05 found that manual reconciliation does not settle both accounting stores. Until that is corrected, do not display “Budget restored”, “Ready to continue” or automatically trigger another paid request. Confirming a charge and successfully resuming work are separate outcomes.

<a id="rf-16"></a>

## RF-16 · P1 · Make notifications understandable from setup to receipt

**Locations:** [notifications.tsx](frontend/src/features/settings/notifications.tsx), all components; [notifications/transport.py](backend/app/notifications/transport.py), `message`/`publish`; [notifications/delivery.py](backend/app/notifications/delivery.py), test and summary bodies.

| Current text | Replacement |
| --- | --- |
| “Notifications” heading | “Daily summary” |
| Introduction mentioning Relevant, Possible, baseline and reassessment | “Get a daily summary of jobs in your shortlist, including relevant jobs and others worth a look.” |
| “The local publisher is configured. Send a test to check server acceptance.” | “Notification sending has been set up. Send a test and check your notification app.” |
| “Configure the notification publisher on the server before sending messages.” | “Notification sending hasn’t been set up. Ask the person who set up Job Finder for help.” |
| “Send a daily summary” | Keep. |
| “Daily summary time” | “Send at” |
| “Timezone” | “Time zone” |
| Timezone validation | “Choose a time zone from the list.” Requires the selector described below. |
| Daylight-saving help | “Your summary follows this local time, including daylight-saving changes.” |
| “Send a summary even when there are no new roles” | “Send a summary even when there are no new matches” |
| Schedule explanation | “Each company is checked on its own schedule. Your summary will mention checks that couldn’t finish.” |
| “Save notification schedule” | “Save summary schedule” |
| “Notification schedule saved.” | “Summary schedule saved.” |
| “Next scheduled summary…” | “Next summary: {dateTime} ({timezoneLabel}).” |
| Enabled but next time unavailable | “Daily summaries are on. The next send time is not available yet.” Do not incorrectly say they are off. |
| Disabled summaries | “Daily summaries are off.” |
| “Test the connection” | “Check notifications on your device” |
| Test explanation | “Send a test message, then check your notification app. This won’t change your summary schedule or mark any job alerts as sent. Your device must be on the same local network or connected through Tailscale. Background notifications depend on your notification app.” |
| “Test notification” | “Send test notification” |
| “Requesting test…” | “Requesting test notification…” |
| “Retry test request” | “Check or retry test request”. Preserve the retained request identity; do not create a second send just to check its status. |
| “Test queued. Its result appears below.” | “Test requested. Its sending status will appear below.” |
| “Delivery history” | “Previous summaries” |
| History helper | “Sending status shows whether the notification service accepted the message. It cannot confirm whether your device displayed it.” |
| “Synthetic assessment results.” | “Includes sample match results, not real AI matches.” |
| “Summary content removed with profile data.” | “The summary text was deleted with your profile data.” |
| “Coverage at cutoff…” | “When this summary was prepared:” followed by the nonzero plain-language counts specified below. |
| “Resend queued.” | “Another send has been requested.” |
| Resend help | “This sends the same summary again. Some jobs in it may have changed since it was prepared.” |
| Unknown-delivery checkbox | “I understand that I may receive this summary twice.” |
| “Resend summary” | “Send this summary again” |
| “Retry resend request” | “Check or retry send request”. Keep the same request identity on an uncertain network retry. |
| “Requesting…” | “Requesting another send…” |

**Behaviour: use a searchable time-zone selector** with readable labels and canonical stored values. Examples: “London” → `Europe/London`, “New York” → `America/New_York`, “Los Angeles” → `America/Los_Angeles`, “Kolkata” → `Asia/Kolkata`, “Sydney” → `Australia/Sydney`, “UTC” → `UTC`. Include the supported IANA zones, not just the six examples. Preserve existing valid saved zones; do not replace them with the browser location. Show the current offset as supplementary text, not as a fixed description that becomes wrong after daylight saving. Until the control exists, use **“Enter a time zone such as Europe/London.”** instead of claiming a mandatory list selection.

**Missing setup information:** the current UI cannot tell a nontechnical user how to subscribe on their device. Add a collapsed **“Set up notifications on your device”** block before the test button:

1. **“Open the ntfy app on your device.”**
2. **“Add a subscription using the server address and topic below.”**
3. Labels: **“Server address”**, **“Topic”**, **“Copy server address”**, **“Copy topic”**.
4. **“Use the notification sign-in details provided by the person who set up Job Finder.”**
5. **“Connect to the local network or Tailscale, then choose ‘Send test notification’.”**

This requires explicit non-secret, **client-reachable** subscription configuration in the backend response. Do not display the internal `http://ntfy:80` address, publisher token, API key or a guessed public URL. If subscription details are not configured, replace steps 2–4 with **“Ask the person who set up Job Finder for the notification server address, topic and sign-in details.”** Do not add a public notification service or change deployment privacy as a side effect of this UX fix.

### Exact sending-state labels

| State | Label | Supporting sentence |
| --- | --- | --- |
| `pending` | “Waiting to send” | Omit a second sentence unless a real planned time is available. |
| `sending` | “Sending…” | No success claim yet. |
| `sent` | “Accepted by notification service” | “Check your notification app. Job Finder can’t confirm whether your device displayed the message.” |
| `failed`, retryable and within actual retry window | “Waiting to try again” | “Next attempt: {time}.” Use `available_at`; do not invent the time or promise a retry past `deadline_at`. |
| `failed`, terminal | “Not sent” | Show the mapped reason below. |
| `unknown` | “Sending result not confirmed” | “The message may have arrived. Check your notification app before sending it again. We won’t resend it automatically.” |
| Prior digest state unknown, latest attempt did not resolve it | “An earlier send may have arrived” | “The latest attempt did not confirm what happened. Check your notification app before sending it again.” |
| `skipped`, content removed | “Summary text deleted” | “This summary can’t be sent again.” |
| `skipped`, content retained | “Summary not sent” | Only give a reason such as “No new matches to send” when stored data identifies that reason. Otherwise show “No message was sent for this summary.” |
| Failed without delivery record, window expired | “Summary not sent in time” | “Jobs that haven’t been sent can be included in a later summary if they still qualify.” |

Move “Attempt {n}” and “Requested by you” to an expandable **“Sending details”** area; retain them for diagnosis without making every user interpret retry bookkeeping.

| Error code | Exact explanation |
| --- | --- |
| `notification_mock_mode` | “Notification sending is off for testing. No message was sent.” |
| `notification_configuration_required` | “Notification sending hasn’t been set up. Ask the person who set up Job Finder for help.” |
| `notification_token_required`, `notification_token_invalid`, `ntfy_rejected` | “The notification service didn’t allow this message to be sent. Ask the person who set up Job Finder to check the connection settings.” |
| `notification_destination_changed` | “The notification connection changed. Ask the person who set up Job Finder to check it before trying again.” |
| `notification_window_expired` | “This summary couldn’t be sent in time. Jobs that haven’t been sent can be included in a later summary if they still qualify.” |
| `ntfy_rate_limited` | “The notification service asked us to wait.” Add the retry sentence only when actually scheduled. |
| `ntfy_connect_failed` | “We couldn’t connect to the notification service.” Add the actual retry state or the action “Send this summary again” if eligible. |
| `notifications_disabled` | “Daily summaries were turned off before this message was sent.” |
| `profile_purged` | “Sending stopped because the profile was deleted.” |
| `notification_message_limit` | “This summary couldn’t be sent because its message was too long. Open Jobs to see your shortlist.” |
| Unknown-outcome codes, including `ntfy_delivery_unknown`, `ntfy_unconfirmed_response`, `ntfy_response_limit`, `ntfy_invalid_receipt` | Use the `unknown` row above; do not call this “Not sent”. |
| Unmapped terminal failure | “This message couldn’t be sent. Check the notification setup before trying again.” |

### Replace the summary content too

Website history and actual notification bodies must use the same labels:

| Existing count | Exact display |
| --- | --- |
| `new` | “{n} newly found matches” (one: “1 newly found match”). This means newly found by Job Finder, not newly advertised. |
| `baseline` | “{n} matches from first checks” (one: “1 match from a first check”). |
| `reassessment` | “{n} new matches after updated checks” (one: “1 new match after an updated check”). |
| `source_errors` | “{n} job pages couldn’t be fully checked” (one: “1 job page couldn’t be fully checked”). |
| `assessment_errors` | “{n} jobs couldn’t be checked for a match” (one: “1 job couldn’t be checked for a match”). |
| `unresolved_companies` | “{n} companies still need a job page” (one: “1 company still needs a job page”). |
| `pending_operations` | “{n} checks still in progress” (one: “1 check still in progress”). These count operations, not unique jobs. |
| `matching_available=false` | “Job matching wasn’t available when this summary was prepared.” |

Do not show four zero-warning counts on every summary. Display only nonzero issue lines. If there are no matches and no issues, use **“No new matches in this summary. You can still browse all jobs.”** If there are no matches but checks failed or remain pending, use **“No new matches are ready for this summary. Some checks haven’t finished.”** followed by the precise issue lines. Missing matching setup uses **“No matches are ready because job matching needs setup.”** instead. Do not call these states “No vacancies”.

Set summary notification title to **“Your daily job summary”** and test title to **“Job Finder test”**. Keep summary body date **“Summary for {readableDate} ({timezoneLabel}).”** End with **“Open Job Finder to view your shortlist.”** Preserve the full UTF-8 size bound; shorten complete lines and append **“More results in Job Finder.”** instead of truncating a job title into a misleading fragment.

Replace test body **“This is a test notification from Job Finder. No job events were consumed.”** with **“Your Job Finder test notification is here. Your daily summary schedule hasn’t changed.”** The statement about arrival is read on the receiving device; the website must still use the server-acceptance wording above.

<a id="rf-17"></a>

## RF-17 · P1 · Centralise errors and progress around the user's task

**Locations:** [lib/api.ts](frontend/src/lib/api.ts), [shared.tsx](frontend/src/features/inventory/shared.tsx), all operation renderers, [main.py](backend/app/main.py), [auth.py](backend/app/auth.py), [api](backend/app/api), [services/operations.py](backend/app/services/operations.py), [ai/provider.py](backend/app/ai/provider.py), [collection](backend/app/collection).

### Required presentation behaviour

1. Preserve `code`, `field_errors` and `request_id` in the client error object. Currently field errors are discarded. Map errors to known user messages and an appropriate action; keep raw details out of the main sentence.
2. Give each field a visible error and accessible association. Expand a collapsed section containing an error. Focus a summary headed **“Check the following details”** whose items link to the fields. Do not show “Check the highlighted fields” when nothing is actually highlighted.
3. Errors describe the operation that failed: loading jobs, saving preferences, reading a CV, sending a summary. `processing_failed` must not suggest uploading a document when a company check failed.
4. Retain input after a failed mutation. For a temporary refresh failure, keep previously loaded content and say **“We couldn’t refresh this page. You’re seeing the last loaded information.”** Action **“Try refreshing again”**. A confirmed expired session still signs the user out and clears private caches.
5. Do not expose Pydantic messages, Python errors, enum names or strings produced with `replaceAll('_', ' ')` as user explanations. Unknown codes get the task-specific fallback below. Put a safe error code and request reference under **“Technical details”**, excluding raw payloads, credentials and personal data.
6. Do not say an action automatically retries unless the current durable state actually schedules a retry. The same error code can appear during automatic retry and after attempts are exhausted. Read `state`, retryability and timing; extend the API if necessary.
7. For uncertain POST/save results, say **“We couldn’t confirm whether this was saved. Check the latest saved version before trying again.”** Do not assert that nothing changed. Preserve request identity for actions whose retries can duplicate work or notifications.

Error-action precedence: an unresolved charge or unknown notification outcome overrides all generic retry actions; a known setup block overrides task retries; a genuinely queued retry uses its scheduled status; only a terminal, retry-eligible failure offers the task-specific retry. This applies even if a lower-level exception was recorded as `processing_failed`.

### Shared and authentication errors

| Code / current message | Exact replacement | Action |
| --- | --- | --- |
| `network_error` | “We couldn’t connect to Job Finder. Check your connection and try again.” | “Try again” for a safe read; use the uncertain-write rule for mutations. |
| Generic `request_failed` / unknown exception while loading | “We couldn’t load {contentLabel}. Try again.” | “Try again”. `{contentLabel}` is one of “your jobs”, “your companies”, “your profile”, “your settings”, “your summaries”; never a URL. |
| Unknown exception while saving, server definitively rejected | “We couldn’t save your changes. Try again.” | “Try saving again”. Keep fields. |
| `invalid_response` | “Job Finder couldn’t read the response. Try again.” | Safe-read retry; unknown-write rule otherwise. |
| `database_unavailable` | “Job Finder is temporarily unavailable. Try again shortly.” | “Try again” for reads. Do not ask the user to repair storage. |
| `unauthenticated` | “Please sign in to continue.” | “Sign in”. |
| `invalid_credentials` | “The username or password is incorrect. Check both and try again.” | Keep the sign-in form; do not identify which credential was wrong. |
| `login_rate_limited` | “Too many sign-in attempts. Please wait 15 minutes before trying again.” | Disable repeated sign-in attempts for the enforced period if timing is available. |
| `invalid_origin` | “This address isn’t approved for Job Finder. Open the link provided by the person who set it up.” | No automatic navigation to an untrusted supplied URL. |
| `invalid_csrf` | “Your security check expired. Reload the page before trying again. Unsaved changes may be lost.” | “Reload page”; preserve/confirm dirty input where possible. |
| `validation_error` | “Check the following details.” | Field-linked summary; do not repeat technical validator phrasing. |
| `revision_required`, `revision_conflict`, `draft_conflict`, `feedback_conflict` | Use RF-11's context-specific comparison message. | “Compare changes” where supported; otherwise confirmed “Load saved settings”. |
| `invalid_cursor` | “This list has changed. Refresh it to continue.” | “Refresh list”. |
| `invalid_idempotency_key`, `idempotency_key_required`, `idempotency_conflict` | “We couldn’t safely confirm this request. Check its current status before trying again.” | Refresh the relevant status; do not ask the user to create a request key. |

Add custom messages for known field constraints instead of relying on library defaults: company name blank → **“Enter a company name.”**; invalid website → **“Enter a full public website address starting with https:// or http://.”**; private/local website → **“Use the company’s public website address. Local network addresses can’t be checked.”**; interval → **“Enter a whole number from 1 to 720 hours.”**; invalid board identifier → **“Enter only the company part of the job-page address, using letters, numbers, hyphens or underscores.”**; invalid model → **“Enter an exact OpenRouter model identifier in the form maker/model.”**; duplicate backup models → **“List each backup model only once.”**; primary duplicated as backup → **“Choose backup models that differ from the main model.”**; invalid provider identifier → **“Enter the provider identifier exactly as listed in OpenRouter.”**; invalid daily requests → **“Enter a whole number from 1 to 10,000.”**; invalid daily budget → **“Enter a daily budget greater than US$0 and no more than US$1,000.”**

For remaining numeric constraints, generate **“Enter a number from {min} to {max}.”**, substituting the actual field limits. For length constraints, **“Use no more than {max} characters.”** For a missing required value, **“Enter {fieldLabel}.”** Use the visible field label; never expose nested paths such as `preferences.criteria.0.description`.

### AI and spending errors

| Code / condition | Exact replacement | Action |
| --- | --- | --- |
| `configuration_required` | “AI hasn’t been set up for {taskLabel}. Choose a model in AI settings, or ask the person who set up Job Finder for help.” | “Open AI settings”. Task labels: “reading your CV”, “reading job pages”, “checking job matches”. |
| `key_required`, `ai_authentication` | “Job Finder couldn’t connect to the AI account. Ask the person who set it up to check the OpenRouter connection.” | “View setup status”. No CV re-upload prompt. |
| `ai_credits` | “The OpenRouter account has run out of credit. Ask the person managing that account to add credit before trying again.” | “View spending”. Do not claim the app's daily budget increase buys credit. |
| `ai_configuration`, `ai_capability`, `ai_model_mismatch` | “The selected AI model couldn’t be used with these settings. Review the model in AI settings.” | “Open AI settings”. |
| `ai_protocol`, `ai_decisions_blocked` | “This AI model needs additional setup before it can be used. Ask the person who set up Job Finder for help.” | “View technical setup”. Never tell a novice to disable a billing safeguard. |
| `ai_catalog_unavailable`, `ai_catalog_invalid` | “We couldn’t check which AI models are available. Try again later.” | Safe retry of catalogue/test setup, not automatic inference. |
| `ai_budget`, daily limit | “Your daily AI limit has been reached. Wait until {resetTime}, or review your spending limits.” | “View spending limits”. Only include a verified reset time. |
| `ai_budget`, cumulative development-validation cap | “The test allowance has been reached. Further live AI tests are stopped.” | “View technical setup”. Never show the daily-reset message or advise resetting the ledger. Requires a distinct reason field/code; current `ai_budget` conflates these causes. |
| `ai_rate_limited`, `ai_unavailable` with actual queued retry | “The AI service is busy or temporarily unavailable. Another attempt is scheduled.” | Show the true time if available. |
| Same errors after terminal failure | “The AI service couldn’t complete this task. Try again later.” | Task-specific retry, subject to billing state. |
| `ai_concurrency` | “Waiting for another AI task to finish.” | No user action required while queued. |
| `ai_cost_unknown`, `ai_transport`, `ai_response_invalid` with unresolved charge | “We couldn’t confirm the charge for an AI request. This task is paused until the charge is checked.” | “Review charges” → spending recovery. No inference retry button. |
| `ai_billing_unavailable`, `ai_cost_pending` | “The final charge isn’t available yet. The reserved amount will stay in your budget until it can be checked.” | “Check charge again” only for the billing lookup, not inference. |
| `ai_schema`, unusable result after validation | “The AI result couldn’t be used. Review the selected model before trying again.” | “Open AI settings”. Do not blame the user's CV without evidence. |
| `ai_input_too_large`, CV task | “This CV is too long for the selected AI settings. Upload a shorter CV, or ask for the model settings to be reviewed.” | “Upload another CV”; “Open AI settings”. |
| `ai_input_too_large`, job match task | “This job description is too long for the selected AI settings. You can still read the listing while the model settings are reviewed.” | “View original listing”; “Open AI settings”. Do not ask the user to shorten an employer's document. |
| `extraction_input_limit`, job-page task | “This job page is too large to read in full with the current settings. Some jobs may be missing.” | “Visit job page”; technical rules/settings available separately. |
| `cost_confirmation_required` | “Confirm that you agree to the possible cost before testing the model.” | Focus the consent checkbox. |
| `billing_changed` | “This charge has already been updated. Refresh the spending information to see it.” | “Refresh spending”. |
| `reconciliation_unavailable` | “This charge can’t be checked automatically. Review its current status or check it in OpenRouter’s billing records.” | “Refresh spending”; manual confirmed-charge section if still unresolved. |
| `mock_mode`, `mock_model`, `mock_fixture_forbidden`, `mock_fixture_missing`, `mock_fixture_invalid` | “The AI test setup can’t complete this task. Ask the person who set up Job Finder to review it.” | “View setup status”. Details can explain missing test fixtures; do not invite users to configure fixture directories or assume sample mode solely from the error code. |

### Job-page and collection issues

Use these mappings wherever an issue appears: company card, page history, extraction preview, discovery result and operation banner. RF-07 handles overlapping codes; do not make a second inconsistent catalogue.

| Codes | Exact replacement |
| --- | --- |
| `incomplete_inventory` | “Some jobs may be missing from this check. Previously found jobs are still available.” |
| `source_unavailable`, `source_http_error`, `generic_http_error`, `fetcher_transport` | “We couldn’t reach this job page. Previously found jobs are still available.” |
| `source_content_type`, `source_invalid_json`, `generic_content_type`, `fetcher_response_invalid`, `invalid_json_ld`, `invalid_job_posting`, `selector_card_invalid` | “Some job details couldn’t be read from this page. Visit the original page to check them.” |
| `source_snapshot_missing`, `source_validator_conflict` | “We couldn’t use the saved copy of this page. A new check is needed.” |
| `source_preview_unavailable`, `extraction_snapshot_missing` | “There’s no usable saved page to test. Choose ‘Check for jobs’, then try the website-rule test again.” In non-preview extraction context: “We couldn’t use the saved page. Choose ‘Check for jobs’ to start again.” |
| `source_rules_invalid`, `source_rules_unsupported` | “The website-reading rules can’t be used for this page. Ask the person who set them up to review them.” |
| `source_cooldown` | “Waiting before checking this page again.” Add the actual next-check time when scheduled. |
| `destination_denied` | “This address can’t be checked safely. Use the company’s public careers page.” Never suggest disabling network protections. |
| `redirect_limit` | “This page redirects too many times. Check the careers-page address.” |
| `html_limit`, `structured_data_limit`, `visible_text_limit`, `job_limit`, `link_limit`, `generic_page_limit`, `generic_link_limit`, `selector_node_limit`, `selector_pagination_limit`, `fetcher_response_large` | “This check reached a reading limit. Some jobs may be missing.” |
| `unstable_pagination`, `invalid_continuation`, `selector_pagination_invalid` | “We couldn’t reliably continue to the next page of jobs. Some jobs may be missing.” |
| `selector_external_pagination` | “The next-page link leads to another website, so this check stopped here.” |
| `job_employer_unverified` | “We couldn’t confirm that some jobs belong to this company. They weren’t added.” |
| `expired_job_evidence`, `selector_closed_listing` | “This page includes jobs marked as closed or past their closing date.” Do not claim existing saved jobs were updated; ER-07 identifies a missing lifecycle transition. |
| `no_verified_generic_jobs`, `selector_no_cards`, `no_structured_jobs` | “We couldn’t recognise any jobs on this page. This doesn’t mean the company has no vacancies.” |
| `ambiguous_reference`, `conflicting_job_posting`, `selector_conflicting_job`, `selector_empty_conflict` | “This page contains conflicting job details. Some results need another check.” |
| `epoch_expired_or_source_changed`, `source_changed`, `collection_superseded`, `extraction_superseded`, `extraction_mode_changed` | “This check stopped because it expired or its settings changed. Choose ‘Check for jobs’ to start a new check.” If the company is paused, action becomes “Edit company” with “Turn job checks back on before starting another check.” |
| `discovery_superseded`, `discovery_changed` | “The company search has changed. Load the latest results before choosing a website.” |
| `search_input`, `search_conflict` | “This company search couldn’t continue. Check the company name and website, then search again.” |
| Any unmapped issue | “We couldn’t finish checking this job page. Previously found jobs are still available.” Technical details contain the actual safe code. |

A `no_structured_jobs` intermediate result may be recoverable by a later AI extraction step. Do not label the overall company check failed until its final state says so. Similarly, a skipped expired listing is an observation, not necessarily a whole-run failure.

### Missing items, cancelled work and other actionable errors

| Codes | Exact replacement and action |
| --- | --- |
| `company_not_found` | “This company is no longer available.” → “Back to companies”. |
| `job_not_found` | “This job is no longer available in Job Finder.” → “Back to jobs”. Do not assert the employer closed it. |
| `source_not_found` | “This job page is no longer available in Job Finder.” → “Back to company”. |
| `draft_not_found` | “This CV draft is no longer available. Return to Profile to choose another draft or upload a CV.” → “Back to profile”. |
| `document_not_found`, `document_deleted` | “The uploaded CV is no longer available. You can upload it again if you need to analyse it.” → “Back to profile”. |
| `draft_not_editable` | “This profile draft isn’t ready to edit. Check its progress or upload another CV.” → “View progress”. |
| `review_required` during approval | “Confirm that you’ve reviewed your experience and preferences before saving this profile for matching.” → focus review checkbox. |
| `review_required` during conflict resolution | “Compare each changed section and choose what to keep before continuing.” → focus first unchosen group. |
| `consent_required` | “Agree to share your CV text with OpenRouter and its selected AI service before analysis can start.” → upload consent; existing uploads that lack valid consent require the explicit re-upload flow, not silent consent. |
| `confirmation_required` | “Type DELETE PROFILE exactly to confirm deletion.” → focus confirmation input. |
| `document_changed` | “This CV draft changed or was deleted while it was being prepared. Return to Profile to see the latest version.” |
| `invalid_profile` | “We couldn’t save this profile. Review your experience and preferences, then try again.” This error comes from activation/save validation, not necessarily an AI failure. Return typed reasons and field errors: missing summary → “Add a short summary of your experience.”; missing desired roles → “Add at least one job title or type of work you’re interested in.”; missing focus industries → RF-10's industry message; invalid supporting evidence → “Some supporting details don’t match this CV. Review the affected profile details before saving.” Do not pass `str(error)` through or send the user to model settings for an incomplete form. |
| `company_paused` | “Job checks are paused for this company. Turn them back on in company settings before checking again.” → “Edit company”. |
| `invalid_region` | “The European website option is available only for Lever.” → focus job-website selector in technical manual entry. |
| `invalid_candidate` | “Choose one of the company websites shown in these results.” → focus choices. |
| `matching_unavailable` | Use RF-03's prerequisite-specific message. |
| `assessment_mode_changed`, `assessment_policy_changed`, `assessment_snapshot_missing` | “This match needs a new check using the current job and profile.” → “Check match”. If either required item no longer exists, use its missing-item message instead. |
| `operation_not_found` | “We couldn’t find the status of this task. Refresh the page to see the latest information.” → safe status refresh. |
| `operation_not_retryable`, `operation_cancelled` | “This task can’t be retried from its current state. Refresh its status to see what to do next.” → refresh; do not promise no earlier paid request was sent. |
| `handler_pending` | “This feature isn’t available yet.” → return to the parent page; technical details may identify the unsupported handler. |
| `call_not_found` | “This AI spending record is no longer available.” → “Refresh spending”. |
| `discovery_not_found` | “This company search is no longer available.” → “Load latest searches”. |
| `delivery_not_found`, `digest_not_found` | “This notification record is no longer available.” → “Refresh summary history”. |
| `notification_changed` | “The sending status changed. Check the latest result before sending again.” → “Refresh sending status”. |
| `notification_not_resendable`, `notification_retry_required` | “This summary can’t be sent again from here. Check its status in Previous summaries.” → that section. |
| `duplicate_acknowledgement_required` | “The summary may already have arrived. Confirm that you accept a possible duplicate before sending it again.” → focus checkbox. |
| `notification_content_removed` | “This summary’s text was deleted, so it can’t be sent again.” |
| `notification_mode_changed` | “This summary was created with different matching settings and can’t be sent again.” |
| `notification_superseded` | “These jobs are already included in another summary, so this one won’t be sent again.” |

### Exact background-operation copy

Replace the generic **“Processing”**, raw `progress` and generic **“Completed”** with task-aware text. A parent job that merely schedules child work is not evidence that checking has finished.

| Actual operation/stage | Exact text |
| --- | --- |
| `profile_ingest`, queued / running / review-ready | “Waiting to read your CV…” / “Preparing your profile…” / “Your profile is ready to review.” |
| `company_discover`, parent accepted/succeeded after scheduling | “A search for job pages has been requested.” |
| `discovery_step`, running | “Looking for this company’s job pages…” |
| A single discovery step succeeds but run is unfinished | “Search step finished. The search for job pages is continuing.” Prefer aggregate run status over showing every step. |
| Discovery run complete/partial | “Job-page search finished.” / “The search finished with some pages left unchecked.” Show actual page count/results separately. |
| `company_check`, schedules `{n}` checks | “Checks requested for {n} job pages.” One: “A check was requested for 1 job page.” This does not say checks are complete. |
| Company check, no sources | “No job page is set up yet. Choose ‘Find job pages’ or add a job page manually.” |
| Company check, sources exist but all disabled | “Automatic checks are off for every job page. Turn on a page to check it.” Requires distinguishing this from a missing source. |
| `source_collect`, running | “Checking this job page…” |
| Page saved, `job_extract` scheduled | “The page was downloaded. Waiting to read its job details…” |
| `job_extract`, running | “Reading job details…” |
| One page completes while collection run continues | “Page checked. More job pages are being checked.” |
| Collection run complete / partial | “Job-page check complete.” / “Check finished. Some jobs may be missing.” |
| `profile_reassess`, schedules `{n}` jobs | “Match checks requested for {n} jobs.” One: “A match check was requested for 1 job.” |
| `job_assess`, queued / running / succeeded | “Waiting to check this match…” / “Checking this job against your profile…” / “Match check complete.” |
| AI validation, queued / running | “Waiting to test the model…” / “Testing the saved model…” |
| Billing lookup, queued / running | “Waiting to check the charge…” / “Checking the charge with OpenRouter…” |
| Generic state polling temporarily fails | “We couldn’t refresh the progress. The task may still be running.” → “Check progress again”. |
| Terminal `processing_failed`, profile task | “We couldn’t prepare your profile. Try again. If it keeps failing, check the CV analysis settings.” |
| Terminal `processing_failed`, company/discovery/page task | “We couldn’t finish this job check. Try a new check, or visit the company’s job page.” |
| Terminal `processing_failed`, matching task | “We couldn’t check this match. You can still read the job listing.” → eligible “Check match” or billing/setup action if known. |
| Terminal `processing_failed`, model test | “The model test couldn’t finish. Review AI settings before trying again.” |
| Terminal `processing_failed`, billing lookup | “We couldn’t check this charge. The reserved amount remains until the charge is confirmed.” |
| Other task, queued / running / terminal failure | “Waiting to start…” / “Working on your request…” / “We couldn’t finish this request. Check its latest status before trying again.” |

The actual `OperationView` lacks retry scheduling time and an aggregate child-completion result. Add structured fields where needed; do not infer either by parsing an English progress string. Keep human-readable backend messages as a fallback for older clients, but make the normal UI use stable kinds/states/reason codes.

## Implementation rules that prevent this returning

1. Create a shared presentation catalogue for statuses, errors, task names and terms. Key it by stable codes and include context where a code has multiple meanings. Avoid separate competing maps in profile, discovery and notifications.
2. Use complete messages with structured variables, not sentence fragments joined with enum strings. Define singular and plural forms explicitly. Hide empty warning lists and unused headings.
3. Keep technical detail retrievable. Error details may include a safe code, request reference and timestamp; never a stack trace, secret, CV text or raw provider response. A normal user should not need this disclosure to understand the next action.
4. Keep externally supplied and generated prose separate from interface-owned copy. Preserve original quotes; add plain-language summaries only with evidence. Prompt changes need semantic checks and versioning where they affect the matching contract.
5. Do not repeat long disclaimers on every row. Keep one accurate scope explanation at the list level, then show concise state-specific warnings when there is an actual issue.
6. Use action labels that describe what actually happens. “Refresh list” reloads saved results; “Check for jobs” requests new collection; “Check match” requests AI assessment; “Test saved model” makes a separate sample request. These must never be interchangeable.
7. Do not invent completion, timing, payment or privacy guarantees to make copy sound polished. Expose missing state as an implementation prerequisite and use the conservative fallback specified above.

## Acceptance checklist for the implementation

These are required future checks, **not tests executed in this review**. Use synthetic data and mocked services by default. They do not authorise paid requests or deployment here.

| Journey | Pass condition |
| --- | --- |
| First visit | Without knowing what a model/source/queue is, the user sees one next step and can reach Profile or All jobs. Missing profile and missing matching setup produce different messages. |
| Test versus real data | No “Development preview” branding; every sample AI result is still unmistakably labelled. Real jobs mixed with sample matches are not described as entirely sample data. |
| CV upload | Supported files, server-side reading, external AI recipients, consent, sample mode and storage timing are clear before upload. Unknown mode blocks upload with recovery. |
| Profile preferences | All enum labels and conflict summaries use the same plain-language terms. Must-have preferences and uncertain information retain the broad-shortlist policy. |
| Save and leave | Save-for-later does not claim profile activation. Active save explains matching updates/cost. Navigation cannot silently lose edited content. |
| Jobs | First-check jobs are not called newly posted. Persistent non-baseline jobs are not indefinitely “new”. Refreshing the list does not suggest that websites were checked. |
| Match explanation | Both chat and Decisions paths show readable text. No UUIDs, “Decisions outcome”, raw `not_met`, JSON objects or internal evidence IDs appear in ordinary explanations. Exact supporting quotations remain accessible. |
| Empty/failure states | Filtered empty, no companies, pending collection, failed collection, no matches and matching unavailable each use their assigned message/action. No failure is described as no vacancies. |
| Companies | A novice can follow a company using a name and optional website. Technical job-board and CSS controls stay collapsed. Existing-page schedules are not misrepresented as changed by the company default. |
| AI configuration | Saving matching settings discloses possible reassessment cost. Testing uses the saved model and needs explicit cost acknowledgement. Unsupported protocol settings are not presented as effective. |
| Billing | Unknown charges direct to charge review, not a blind inference retry. Small positive spend never displays as zero. Daily and cumulative test caps have different messages. |
| Notifications | The user can identify how to subscribe or whom to ask. Accepted by service never becomes delivered to phone. Unknown sends require a duplicate acknowledgement and preserve request identity. |
| Data deletion | File-only and profile-wide deletion use different confirmations. Copies held in backups/external services/devices are not falsely claimed deleted. |
| Validation | Backend field errors survive the client boundary, open the relevant section and identify the actual field. User input survives failures. |
| Presentation | Check the new strings at 375px and desktop, with keyboard navigation and 200% zoom. Long titles/names and singular/plural counts remain readable. Buttons' accessible names match their visible actions. |
| Regression sweep | Search interface-owned strings for `development`, `mock`, `synthetic`, `revision`, `reconcile`, `inventory`, `source`, `adapter`, `schema`, `protocol`, `queued`, `publisher`, `IANA`, `MiB`, `idempotency`, `generation`, `not_met` and raw `replaceAll('_', ' ')`. Each remaining use must be in deliberate technical detail, a real brand/URL, or an unchanged quotation—not normal task copy. |

## Evidence and review limits

Reviewed the app shell, sign-in/error boundary/API wrapper; every inventory, discovery, source-rule, profile and settings feature; backend API/operation errors; parser errors; native and chat matching explanations; notification history and generated messages. Read the requirements and decision records to retain broad matching, personal hosting, CV consent and conservative uncertainty. Existing development/browser evidence was considered but not rerun.

Applied [Impeccable clarify](.agents/skills/impeccable/reference/clarify.md), local ui-ux-pro-max feedback/error guidance, and the public [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md). The latter's relevant principles are specific action labels, actionable error recovery and accessible feedback. Product sentence case is retained rather than adopting its title-case preference.

The download-disabled Impeccable context command exited 127 without output. No PRODUCT.md or DESIGN.md was found in the inspected skill/application trees, so existing CONTEXT.md/UI_UX.md and source were used. The ordinary shell sandbox failed before execution with the known `bwrap` loopback error; permitted read-only expanded execution was used. No dependency fetch, installation, build, app runtime, live AI request or notification send occurred. This review updates only this report and the review checkpoint in PROGRESS.md; pre-existing changes remain untouched.

Implement P1 consequence/error/state changes first, then the P2 vocabulary and presentation changes. The deliverable is complete when the specified user journeys satisfy the acceptance table—not when a string search alone is clean.
