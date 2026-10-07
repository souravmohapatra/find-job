# UI/UX implementation requirements

## Direction and foundation

Polished, minimalist, content-first. Use React/TypeScript, Tailwind CSS, shadcn/ui with Radix, and Lucide. Use a local system sans-serif stack; no external fonts or analytics. Start with a light neutral theme, dark readable text, one muted blue action accent, subtle borders, an 8px spacing rhythm and restrained rounding. Define semantic colour/spacing/type tokens centrally; do not scatter hex values in components. Dark mode is deferred until it can be tested independently.

The ui-ux-pro-max minimalist style guidance informs hierarchy and interaction quality. Stack guidance supports explicit asynchronous/form state; it does not require server-rendered React in this Vite client. All compliance and polish checks below are planned, not executed.

## Navigation and routes

- `/jobs`: default relevant feed; Shortlist / All jobs switch, company/search/availability filters.
- `/jobs/:id`: dedicated detail route, preserving list filters and scroll position on return.
- `/companies`: company list with counts, status, interval and next/last check.
- `/companies/:id`: company identity, sources and job list with its own visible Shortlist / All jobs switch.
- `/profile`: reviewed experience, future preferences, domain diversification and CV replacement.
- `/settings`: notifications, timezone, processing/search status, per-task AI model configuration and non-secret operational preferences.

Use a compact side navigation on desktop and a labelled mobile navigation/drawer. Avoid a separate dashboard of decorative metrics. Primary content should be jobs and actionable state.

## Setup

Guide through CV upload, profile review, preferences, then first company. Show extraction progress and allow recovery from parser/model errors. Facts, inferred/unknown values and user changes are distinguishable. Keep saved input when requests fail. Activation requires reviewed summary and one desired role/function; other constraints may be unrestricted.

Profile has separate Experience and Preferences sections. Domain controls use “Focus on selected domains”, “Prefer selected domains, explore others”, and “Open to any domain” with short explanations. Open is the default, visibly reviewable before save. Required versus preferred criteria is a per-field choice where relevant. Advanced criteria are progressively disclosed.

Replacing a CV opens a comparison draft; accepting selected changes creates a revision and queues reassessment. It does not silently erase preferences. Save feedback indicates that matching is updating, while jobs remain browsable.

## Job list and detail

Desktop uses compact rows with title, company, location, first-seen information and a short match reason; mobile stacks the same information into simple cards. Show labelled category badges rather than percentages. Shortlist includes match and possible_match, ordered by recency. Use “Relevant” / “Possible” labels rather than fine-grained ranking. Broad inclusion is the default; an advanced threshold control starts at 30/100 and explains it as approximate relevance, not a probability. Clearly unrelated job functions remain excluded even above that score. All jobs includes unassessed/error/not-match entries; remaining filters are visible and clearable. Availability defaults to active/unknown with an explicit all-status option for closed jobs.

Use 30 results per page with accessible pagination/Load more; no endless automatic scrolling. URL query parameters preserve view and filters. Detail includes source link, advertised date when known, first/last seen, structured description, why it fits, gaps, unknowns, current profile revision status, and Relevant / Not relevant feedback. Original source opens safely in another tab. Do not auto-reorder the list while the user is reading; offer a new-results indicator.

## Companies and status

Adding a name or URL opens a compact form with daily interval default. Ambiguous discovery asks for identity selection; missing sources retain the request and show the next attempt. Allow source correction, pause, interval change and Check now. Unsupported sources remain visible with an explanation.

Distinguish: no matches; successful empty inventory; no source; partial collection; failed check; assessment pending/failed/outdated; notification failed/unknown. Show last successful check, not just last attempted check. Loading placeholders must not replace usable cached content. A pending operation has a stable status display and retry action when appropriate.

## Interaction and accessibility gates

Use labelled form controls, inline errors and a focused error summary for multi-field failures. Preserve user edits on conflict/error. TanStack Query manages server state; React Hook Form/Zod manages draft forms; server validation remains authoritative. Avoid optimistic confirmation for profile activation or source checks.

Meet WCAG 2.2 AA as the implementation target: keyboard journeys, visible/unobscured focus, semantic landmarks, screen-reader labels and status announcements, normal text contrast at least 4.5:1, non-colour status indicators, 44px primary touch targets, zoom and reduced-motion support. Use short opacity transitions only where helpful. Validate 375px, 768px and 1440px layouts and long company/job names; no horizontal page scroll.

API keys stay in deployment secrets; model selection belongs in Settings, not job cards. Provide separate model selectors for Profile analysis, Job extraction, and Job matching; show unset/incompatible/ready states and per-task usage/cost. A model update explains whether existing jobs will be reassessed. Never silently select an account-default model. The UI explains at upload that extracted CV text and relevant profile/job data are sent to OpenRouter and its routed provider, and links to retention/privacy controls. ntfy settings show a daily time picker defaulting to 19:00, an editable IANA timezone, next scheduled send in local time, an empty-summary toggle, a Test notification action, and honest client-connectivity/delivery limitations. Daily/twice-daily collection controls remain separate. The digest includes both Relevant and Possible entries.

## Implemented profile conflict interaction

An editor captures the revision it opened with and retains form data when background queries refresh. A conflicting save offers “Compare saved changes.” The comparison shows local values, current saved profile values, and saved draft values when applicable. Each differing field/group needs an explicit choice; no selection defaults to overwriting another edit. Continuing updates the editing base (and atomically reconciles a draft when present), but never activates a profile. The owner must review and confirm the resulting form again before saving/approval. Further concurrent changes are rejected with edits/choices retained so the comparison can be refreshed. Facts copied from a different CV's reviewed profile become owner-confirmed corrections rather than borrowing that document's source quotes.

## Implemented inventory portal checkpoint

Companies now supports retained watch creation, interval/pause edits, explicit known ATS source entry, source settings/history and manual check status. All jobs and detail use real inventory APIs with URL-backed company/search/availability filters and safe external source links. Descriptions are plain text; absent assessment is explicit. Background query failures announce without stealing focus, while failed mutations focus their error summary. Source edits capture a revision when first changed and survive background refreshes. Counts, fuller coverage summaries, company-level job tabs, scroll restoration/new-results indicators remain follow-up work alongside actual collection/matching. The current main bundle needs route splitting before release polish is complete.

## Assessment and feedback interaction

Job rows label Relevant, Possible, Not a match, stale and operational states. Detail exposes cited duties, coarse relevance, reasons, transferable experience, gaps and criterion outcomes, with supporting quotations behind disclosures. Mock results are explicitly labelled. Unassessed/stale listings remain readable and offer reassessment; queued/running work polls until terminal, while failures show safe errors and recovery links.

Feedback requires a relevance choice and optionally accepts a reason. Saving does not change matching or preferences. Dirty feedback preserves its original revision and input during refresh/conflict; explicitly discarding edits reloads saved feedback. Failed mutations focus the error. Purging the profile clears job explanations/feedback caches and the confirmation copy names the removed data.
