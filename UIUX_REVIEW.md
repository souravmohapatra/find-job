# UI/UX review and improvement suggestions

Reviewed: 2026-10-12 · Source baseline: `e6b1fa9` · Scope: frontend code and synthetic browser journeys.

The interface has a coherent, restrained visual foundation and unusually careful explanations of collection, matching and delivery uncertainty. The highest-value improvements are to preserve work, make validation recoverable, retain useful content during temporary failures, and bring jobs into view sooner. A visual rewrite is unnecessary.

This is a review, not an implementation plan accepted by the owner. Recommendations below have not been implemented. Existing deployment and real-world acceptance gates remain unchanged.

## Method, skills and limits

Applied all three UI/web skills installed under this project's `.agents/skills`, plus the relevant shared UI/UX skill:

| Skill | Application to this review |
| --- | --- |
| [High-end Visual Design](.agents/skills/high-end-visual-design/SKILL.md) | Hierarchy, spacing, typographic precision, responsive composition and restrained component polish. |
| [Impeccable](.agents/skills/impeccable/SKILL.md) | Technical audit workflow and Operate-mode guidance: task completion, consistency, accessible states and purposeful visual hierarchy. |
| [Web Design Guidelines](.agents/skills/web-design-guidelines/SKILL.md) | Fresh [Vercel Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md), applied to source locations and interaction behavior. |
| [UI/UX Pro Max](/home/soumoh02/.codex/skills/ui-ux-pro-max/SKILL.md) | Local guidance on focusable error summaries, inline error associations and React error handling. The first React query returned generic state guidance; a narrower query supplied applicable error-handling guidance. |

[UI_UX.md](UI_UX.md) takes precedence over conflicting aesthetic defaults. Retain the system font stack, Lucide icons, neutral light theme, muted blue accent and subtle decorative borders. High-end Visual Design's mandatory display fonts, nested bezels, pill controls and long entry animations conflict with this task-focused product; they are not recommended. Dark mode is explicitly deferred. No generated imagery is needed for this review.

Impeccable's download-disabled `context` and `detect --json frontend/src` attempts both exited 127 without output. Its engine/detector was unavailable; this is a manual audit with independent browser evidence, not a successful automated Impeccable scan or the standalone dual-assessment `critique` command. No skill context files were generated.

Inspected authentication, routing, shared CSS/buttons/errors, job list/detail, companies/coverage/discovery/source rules, profile upload/edit/conflicts/data controls, notifications, model settings/billing, and existing frontend tests. Browser coverage used installed headless Chrome, synthetic API interception and a temporary local Vite server. No backend data, real CV, credentials, paid provider requests or notification sends were used.

### Evidence actually collected

| Check | Result and boundary |
| --- | --- |
| Existing `npm run test:e2e -- --output=/tmp/jobfinder-uiux-foundation` | **3 failed**, exit 1. At 375/768/1440px, `foundation.spec.ts:67` expected the Jobs heading to receive focus after navigation; it remained inactive. Earlier login axe checks passed. Later layout/axe/settings/logout assertions were not reached. |
| Temporary `node /tmp/jobfinder-uiux-inspect.mjs` | Exit 0. Six populated surfaces at each of 375/768/1440px, height 900px: Jobs, Companies, company detail, job detail, Profile and Settings. All 18 axe scans returned zero violations; ordinary fixtures had no horizontal overflow. No unexpected requests or page errors. |
| Targeted interactions in that inspection | Reproduced unsaved profile loss, hidden validation errors, cached company content disappearing after a failed poll, main receiving focus instead of the lazy-loaded heading, and long-title overflow. |
| Manual screenshot inspection | Reviewed current desktop/mobile jobs, mobile companies/profile/settings, tablet jobs and desktop job detail. Measurements below come from rendered DOM, not estimates. |
| Contrast calculation from CSS tokens | Border on white: **1.304:1**. Muted text on white: **5.895:1**; muted text on page background: **5.548:1**; accent on white: **6.453:1**; body text on white: **14.629:1**. |

Temporary screenshots and machine-readable observations are in `/tmp/jobfinder-uiux-review/`; failing-suite traces are in `/tmp/jobfinder-uiux-foundation/`. These are local, disposable evidence, not tracked assets. The inspection script contains synthetic fixtures and blocks external requests. Its browser/server were closed on completion.

Zero axe violations does **not** establish WCAG conformance or reliable interaction. Physical touch, screen-reader use, Safari/Firefox, 200–400% browser zoom, slow-device performance, actual provider responses, notification delivery, and full backend integration were not exercised. Advanced source-rule/billing/conflict states were reviewed in source and existing tests, not freshly exercised end to end.

## Assessment and priorities

**Implementation integrity: coherent product-specific foundation, with interaction gaps.** Independent collection and matching, transferable experience, visible uncertainty, and explicit conflict choices express the product well. The repeated large panels give browsing and configuration similar visual importance, and some resilience promises do not survive navigation or refetch errors.

The following scores are qualitative audit judgments, not compliance or performance measurements. Theming is assessed against the agreed light-theme scope.

| Dimension | Score / 4 | Main observation |
| --- | ---: | --- |
| Accessibility | 2 | Good labels and native controls; hidden validation and low-contrast input boundaries need attention. |
| Performance | 3 | Lazy route chunks and bounded API pages are sensible; accumulated list rendering has no measured performance result. |
| Theming | 3 | Central color tokens and consistent light identity; component states and spacing/type tokens remain incomplete. |
| Responsive design | 2 | Ordinary fixtures fit all three widths; long headings overflow and mobile content starts too far down. |
| Implementation integrity | 2 | Strong domain semantics, but edit persistence and cached-content handling are inconsistent. |
| **Total** | **12 / 20** | **Acceptable foundation; significant usability work remains.** |

**14 findings: 0 P0, 5 P1, 8 P2, 1 P3.** P1 means substantial user difficulty or an evidenced accessibility problem; P2 means friction with a workaround; P3 is optional polish. Several issues can be fixed in shared components without redesigning the application.

## P1 — address before calling the affected journeys dependable

### R01. Validation can fail invisibly inside collapsed sections

**Evidence — browser-confirmed.** `frontend/src/features/profile/editor.tsx:300`, `:742`, `:767`: open “Location, seniority and other criteria”, add a preference, leave its description blank, collapse the section, acknowledge review, then save. The schema rejects the input, but the error remains hidden, no alert/summary appears, and focus stays on Save profile. `Field` at `:210` renders help/error IDs but does not consistently associate them with its children; selected domains, criteria and numerical controls lack the associations present on summary/desired roles.

**Impact.** The user cannot see why the save did nothing. Keyboard and assistive-technology users have particularly poor recovery. This implicates [WCAG error identification](https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html) and contradicts the project's focused error-summary requirement.

**Suggestion.** Add an invalid-submit handler that opens disclosures containing errors and focuses a linked error summary. Give every failing control `aria-invalid` and references to both help and error text. Preserve all values. Apply the same policy to advanced AI numeric settings, where browser validation can also encounter collapsed controls; that second case is a source-based risk, not a fresh reproduction.

**Acceptance.** The reproduction above displays an actionable error, its link reveals/focuses the criterion, and correcting it permits save. Verify multiple errors and screen-reader announcements.

### R02. Unsaved edits disappear when leaving an editor

**Evidence — browser-confirmed for Profile.** `frontend/src/features/profile/page.tsx:225`, `:289`, `frontend/src/features/profile/editor.tsx:265`: change the professional summary, navigate to Jobs, return to Profile and reopen editing. The saved summary replaces the unsaved text without warning. “Back to saved profile” also unmounts the editor directly. No route/unload guard exists in `frontend/src`. Settings, company/source edits and feedback also hold drafts locally; these need the same review.

**Impact.** A user can lose substantial corrections while checking a job or model setting. Conflict preservation already implemented inside a mounted form does not protect navigation.

**Suggestion.** Track dirty state and provide Stay / Discard changes for navigation and explicit back/cancel actions; use unload protection where supported. Optionally retain drafts in a session-scoped in-memory store across routes. Do not silently activate profiles or put CV content in persistent browser storage. Clear retained drafts on logout/purge.

**Acceptance.** Dirty forms survive canceled navigation; explicit discard works; successful save clears the guard; unchanged forms navigate freely. Include profile drafts, feedback and notification/model settings.

### R03. Temporary refresh failures remove useful cached pages

**Evidence — browser-confirmed for company detail.** `frontend/src/features/inventory/companies.tsx:353`, `:404`: after a successful load, returning a synthetic 503 on the next five-second poll replaces the company and its embedded jobs with an error page. `frontend/src/features/inventory/jobs.tsx:272`, `frontend/src/features/profile/page.tsx:278` and `frontend/src/features/settings/ai.tsx:357` likewise choose an error branch even when cached data may exist. `frontend/src/app/app.tsx:133` can replace the entire shell on a transient session-query error.

**Impact.** Reading is interrupted; mounted editors may disappear. A brief LAN interruption looks like data loss and forces unnecessary retries.

**Suggestion.** Separate initial-load errors from background refresh errors. Keep previously loaded content and drafts visible with a concise “Could not refresh; showing last loaded data” notice and retry. Handle authentication expiry separately: never preserve sensitive content after a confirmed unauthorized session. Avoid treating missing status data as a verified mode.

**Acceptance.** A simulated background 503 preserves content, scroll and local input; a first-load failure still has recovery; a confirmed 401 returns to sign-in and clears private caches.

### R04. Empty input boundaries have insufficient contrast

**Evidence — CSS calculation and rendered forms.** `frontend/src/styles.css:19`, `:60`, `:466`: inputs and textareas use `--border: #dce2e9` against white form panels and white interiors, producing **1.304:1**. Empty controls depend on that boundary to identify the input area.

**Impact.** Low-vision users may struggle to locate the field itself, even though its label and entered text are readable. Necessary control-identification cues require 3:1 under [WCAG non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).

**Suggestion.** Introduce a distinct `--control-border` token with at least 3:1 contrast on the adjacent surface, or provide another sufficiently contrasting identification cue. Keep decorative panel separators subtle; this finding does not require darkening every card border. Retain the existing strong focus treatment.

**Acceptance.** Check empty, filled, error and focused controls using computed colors, including textarea and native select styling. Disabled controls are a separate case.

### R05. Long detail headings cause horizontal page overflow

**Evidence — browser-confirmed.** `frontend/src/features/inventory/jobs.tsx:285`, `frontend/src/features/inventory/companies.tsx:414`, `frontend/src/styles.css:81`: detail titles inherit balanced wrapping but no emergency word breaking. A 203-character unbroken synthetic job title expanded the document from **375px to 3008px**. List headings already have `overflow-wrap: anywhere`; detail headings do not.

**Impact.** Imported content can push the page sideways and make mobile reading/navigation difficult. This is a concrete reflow defect; formal [WCAG reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) validation should also include a 320 CSS-pixel viewport.

**Suggestion.** Apply appropriate wrapping and `min-width: 0` to dynamic heading/container primitives. Preserve the complete title in detail views. Fix the overflowing content rather than masking it with page-level overflow hiding.

**Acceptance.** Long titles/company names, URLs, Unicode and unbroken identifiers fit 320/375/768px widths and zoomed layouts without horizontal page scrolling.

## P2 — improve clarity and task efficiency

### R06. Route focus is not synchronized with lazy content

**Evidence.** `frontend/src/app/app.tsx:33`, `:101`: `RouteFocus` runs outside Suspense on pathname change. If the destination heading has not mounted, it focuses `main` and does not run again when the lazy page resolves. The existing browser suite fails all three heading-focus assertions; the separate inspection confirmed `main` receives focus.

**Impact.** The intended heading announcement and navigation contract are unreliable. Main is a meaningful fallback, so this is not evidence of a keyboard trap or automatically a WCAG failure.

**Suggestion.** Coordinate destination focus with mounted route content. Preserve the existing job-list return-focus/scroll restoration as an intentional exception; do not let a global heading focus steal it.

**Acceptance.** Cold and warm route navigation, delayed chunks, detail loading and browser Back behave predictably. The existing three assertions pass without arbitrary sleeps or weakened expectations.

### R07. Navigation and control panels dominate the first viewport

**Evidence — measured and visually inspected.** `frontend/src/styles.css:230`, `:287`, `:308`, `:357`, `:394`; `frontend/src/features/inventory/jobs.tsx:114`; `frontend/src/features/inventory/companies.tsx:48`. At 375×900, the first job begins at **y=1007px** and the first followed company at **y=1003px**. At 1440×900, the first job begins at **y=730px**. The mobile shell alone precedes the content with branding, four navigation items, account/sign-out and another workspace bar. At 768px, a 232px sidebar plus 96px content padding leaves about 440px for the task.

**Impact.** A returning user sees administration before the jobs or companies they came to inspect. The same large `.panel` treatment on filters, job rows and forms produces excess scrolling and weak hierarchy.

**Suggestion.** Make the mobile account controls compact, combine redundant workspace chrome, and retain four clearly labelled destinations. Use a compact search/availability toolbar, with extra filters disclosed on mobile. Collapse the company-add form behind “Follow company” when watches exist; keep it open for the empty state. Introduce a compact desktop JobRow and a stacked mobile equivalent. Consider a wider breakpoint for switching away from the desktop sidebar.

**Acceptance.** With ordinary populated data, a useful job/company entry appears in the first 375×900 viewport. Primary controls retain the project's 44px touch target, readable labels and visible keyboard focus. This 44px product target is stricter than the [WCAG AA minimum-target rule and its exceptions](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

### R08. The reason to consider a job is buried

**Evidence.** `frontend/src/features/inventory/jobs.tsx:195`, `:215`, `:298`: list rows show a small assessment label alongside date and availability, but no short match reason. The outlined badge highlights “Initial inventory”/“New listing”. Detail puts the entire job description before `AssessmentPanel`, so a long description pushes the product's main decision support far down.

**Impact.** Users must open and scroll through many listings to understand why they were shortlisted. Relevant and Possible do not have the visual prominence required for quick review.

**Suggestion.** Promote the fit label and one existing, evidence-backed reason in each row. Show a compact “Why consider this role” summary near the detail header, then description and full evidence. Retain uncertainty, gaps and original-source links. Limit description prose width to roughly 65–75 characters on wide screens. Do not generate additional AI summaries solely for presentation or introduce probability-like scores.

**Acceptance.** A user can identify employer, location, Relevant/Possible and a reason while scanning. Pending, failed and outdated assessments remain explicitly distinct. Shortlist membership still includes both categories.

### R09. First-run guidance lacks a clear next step

**Evidence.** `frontend/src/app/app.tsx:145` always opens Jobs; `frontend/src/features/inventory/jobs.tsx:167` offers generic Profile/Settings recovery; `frontend/src/features/profile/page.tsx:248` completes a save with a notice and no first-company action. The initial flow is spread across three destinations without a visible completion sequence.

**Impact.** A new owner has to infer how uploading/reviewing a CV, configuring matching and following a company connect. Someone with no companies sees filters before an actionable setup path.

**Suggestion — product improvement, not a proven task blocker.** Add a small dismissible setup checklist driven by real saved state: review profile, confirm preferences/model readiness, follow the first company. Link each incomplete step directly to its control. After profile approval, offer “Follow your first company” when appropriate. Keep All jobs accessible and show completed steps without forcing a wizard.

**Acceptance.** Empty installation, profile-ready/no-company, company-ready/no-profile and matching-unavailable states each identify one sensible next action without asserting there are no vacancies.

### R10. The global company filter exists only in URLs

**Evidence.** `frontend/src/features/inventory/jobs.tsx:31`, `:116`, `:129`: the list reads `company_id` and shows an applied-company label, but offers no selector to choose/change a company from Jobs. A user must navigate through Companies or already have a filtered URL.

**Impact.** Switching between followed employers interrupts browsing, despite company filtering being part of the specified primary jobs workflow.

**Suggestion.** Add an accessible company selector populated from followed companies, with an “All companies” option, an applied-filter indicator and clear action. Keep URL-backed state. On `/companies/:id`, retain fixed company scope and omit the global selector.

**Acceptance.** Choosing, clearing, sharing and navigating Back through filters reproduces the view. Clearing search/status on company detail never changes the route company. Do not add a new UI library solely for this control.

### R11. Environment and freshness labels can mislead

**Evidence.** `frontend/src/app/app.tsx:98` always renders “Development preview”, independently of reported environment. `frontend/src/features/inventory/jobs.tsx:219` renders “New listing” for every non-baseline job, with no time/read-state condition.

**Impact.** The shell label can conflict with Settings' “Live integrations”, and an old non-baseline listing can continue to look new. This is a code-level labeling problem; no production mode was enabled during this review.

**Suggestion.** Distinguish release maturity from integration mode. If “Development preview” means product maturity, use clearer release wording; if it means environment, derive it from trusted status. Show mock/live status only when known. Rename the non-baseline label to a factual discovery label/date, or define and implement a deliberate freshness rule. Keep baseline semantics where they explain digest behavior.

**Acceptance.** Mock, live, status-unavailable, baseline and old non-baseline fixtures show mutually consistent labels. No new provider request is needed to test these states.

### R12. Settings needs section navigation and clearer model selection

**Evidence.** `frontend/src/features/settings/page.tsx:16`, `frontend/src/features/settings/ai.tsx:125`, `:374`: Connection, Notifications, three model forms, limits, usage and billing recovery occupy one long page. The synthetic mobile page is **4962px** tall with advanced model sections closed. Model IDs are free-text fields, and links from matching recovery open the top of Settings.

**Impact.** The user must scroll past unrelated controls to solve a specific setup problem and must recall exact identifiers. Operational detail has nearly the same prominence as daily preferences.

**Suggestion.** Add URL-addressable sections or a compact in-page navigation: Notifications, AI models, Limits & usage, Recovery. Deep-link matching errors to Job matching. Lead each model block with task, saved model and readiness; explain disabled validation beside the action. Suggest already-configured/cached model identifiers while keeping manual entry and independent per-task choices. Do not hardcode unverified recommended models or fetch provider metadata just by opening this page.

**Acceptance.** Direct links land at the relevant section with useful focus; edits survive section navigation; budget/recovery warnings remain visible. Advanced provider/token controls stay available.

### R13. Appended results do not announce their progress or outcome

**Evidence.** `frontend/src/features/inventory/jobs.tsx:237` disables “Load more jobs” during fetch but retains its label. The list has no appended-count status. `frontend/src/features/inventory/companies.tsx:115` uses the same pattern. Both accumulate loaded pages in the DOM.

**Impact.** Keyboard/screen-reader users receive little indication that new entries arrived, where they begin, or that the list has ended. Visual users also lack result-count context.

**Suggestion.** Use “Loading more…” during the request and a separate polite status such as “30 more jobs loaded; 60 shown”. Keep focus stable and provide a predictable way to reach appended entries. Announce completion and keep existing results on failure. Display loaded counts honestly; do not invent a total the API does not supply. Profile long loaded lists before choosing virtualization, since virtualization could complicate the working return-position behavior.

**Acceptance.** Loading, success, empty next page, final page and failure are understandable without visual inference. Repeated pagination preserves focus and reading position. No performance defect is claimed without measurement.

## P3 — optional consistency pass

### R14. Extract shared presentation rules after the usability fixes

**Evidence.** `frontend/src/styles.css:2` centralizes colors but not spacing/type/radius roles. Form layouts alternate between pixel/rem spacing; error output varies among `.error`, `.field-error`, unstyled alerts and `.form-error` (used in notification components without a matching stylesheet rule). Only Button is a shared UI primitive; Profile's `Field` is local. The primary button uses literal `white` rather than an on-accent token.

**Impact.** New features are likely to repeat validation, spacing and status inconsistencies. The current appearance is coherent enough that this is a maintenance/polish opportunity, not grounds for a large refactor.

**Suggestion.** Incrementally define Field, ErrorSummary, StatusNotice, SectionHeader, JobRow and a labelled status-badge vocabulary. Add semantic control-border/on-accent/spacing/type tokens while touching affected components. Keep one system sans family and a restrained hierarchy. Choose a deliberate destructive-action variant for confirmed data removal without changing existing confirmation safeguards. Use localised number/currency formatters for accounting displays, retaining sufficient decimal precision for small charges.

**Acceptance.** Shared components cover error/help associations and their states; no extra dependency or wholesale component migration is required. Decorative motion remains optional and respects reduced motion.

## Suggested visual direction

Refine the current interface into a compact reading-and-review workspace. Its identity should come from understandable match evidence and trustworthy status, supported by careful spacing and typography.

| Surface | Suggested information order |
| --- | --- |
| Jobs | Page title and Shortlist/All jobs → compact search/company/status controls → loaded count/refresh → compact job rows with fit reason. |
| Company detail | Company identity/actions → concise coverage warning or success → jobs → source/settings/history disclosures. |
| Job detail | Title/company/location → fit summary and key uncertainty → source/application links → readable description → full evidence, feedback and history. |
| Profile | Saved profile/preferences summary or the next setup step → focused editor → optional replacement CV/storage controls. |
| Settings | Section navigation → chosen section's essential controls → explicit advanced options and relevant recovery. |

Use whitespace to separate decisions, not to give every datum its own large box. Retain subtle decorative borders, strengthen interactive boundaries, and give uncertainty text a consistent place. Keep Relevant/Possible labels textual even if distinct status colors are introduced. Do not add ornamental charts, stock photography, gradients, glass overlays, mandatory entrance animations or a new dashboard.

## What should be preserved

- Collection remains independent of matching; All jobs includes otherwise filtered assessment states, and missing matching configuration offers a direct escape to collected jobs.
- The profile clearly separates experience from future preferences. Domain diversification remains generic and explicitly reviewable.
- Existing conflict comparisons require explicit choices and preserve edits while mounted; extend this strength to navigation and outages.
- Notification UI distinguishes server acceptance from device delivery, explains unknown outcomes and requires duplicate acknowledgement before ambiguous resends.
- Source-rule preview, saved-rule comparison and advanced disclosure are sound patterns. Keep technical extraction controls away from everyday browsing.
- Native links, buttons, labels, fieldsets/details, password autocomplete, a skip link, visible focus, 44px button sizing and reduced-motion support provide a useful accessibility foundation.
- URL-backed job filters, explicit Load more, safe external links, and job return-scroll/focus behavior deserve regression coverage during changes.
- Current text contrast is good. Light-only theming, local fonts, no heavy imagery and route splitting suit a private task-focused application.

## File-oriented review index

These locations are against `e6b1fa9`; detailed impact and acceptance guidance is above.

### `frontend/src/app/app.tsx`

- `frontend/src/app/app.tsx:33` — R06: focus effect precedes lazy destination content.
- `frontend/src/app/app.tsx:98` — R11: unconditional environment/release label.
- `frontend/src/app/app.tsx:133` — R03: transient session-query errors replace the workspace.

### `frontend/src/features/profile`

- `frontend/src/features/profile/editor.tsx:210` — R01: help/errors are not consistently associated with controls.
- `frontend/src/features/profile/editor.tsx:300` — R01: invalid submit does not reveal hidden errors.
- `frontend/src/features/profile/page.tsx:289` — R02: leaving the editor discards unsaved values.
- `frontend/src/features/profile/page.tsx:248` — R09: successful setup lacks a next-company action.

### `frontend/src/features/inventory`

- `frontend/src/features/inventory/jobs.tsx:129` — R10: no visible company selection control.
- `frontend/src/features/inventory/jobs.tsx:195` — R07/R08: oversized rows and no short match reason.
- `frontend/src/features/inventory/jobs.tsx:219` — R11: non-baseline is presented as perpetually new.
- `frontend/src/features/inventory/jobs.tsx:237` — R13: pagination lacks loading/outcome announcements.
- `frontend/src/features/inventory/jobs.tsx:285` — R05: unbounded dynamic detail heading.
- `frontend/src/features/inventory/jobs.tsx:298` — R08: full description precedes decision support.
- `frontend/src/features/inventory/companies.tsx:48` — R07: always-expanded add form precedes watched companies.
- `frontend/src/features/inventory/companies.tsx:404` — R03: background poll errors hide cached company/jobs.

### `frontend/src/features/settings`

- `frontend/src/features/settings/page.tsx:16` — R12: long settings page lacks section navigation.
- `frontend/src/features/settings/ai.tsx:125` — R12: model entry depends on identifier recall.

### `frontend/src/styles.css`

- `frontend/src/styles.css:19` — R04: decorative border token also defines insufficiently contrasted input boundaries.
- `frontend/src/styles.css:81` — R05: detail heading has no emergency wrapping.
- `frontend/src/styles.css:357` — R07/R14: one large panel treatment serves many different content roles.
- `frontend/src/styles.css:394` — R07: mobile shell/control stack postpones primary content.

## Recommended sequence and future verification

1. **P1 — `$impeccable harden`:** R01–R03, preserving form state and cached content, revealing errors. Keep current backend concurrency/privacy protections.
2. **P1/P2 — `$impeccable adapt`:** R04–R07, accessible input boundaries, heading reflow, mounted-route focus and responsive density. Reuse the existing browser assertions.
3. **P2 — `$impeccable clarify` and `$impeccable onboard`:** R08–R11, evidence-first job presentation, truthful labels, company filtering and setup guidance.
4. **P2 — `$impeccable distill`:** R12–R13, focused settings sections and informative result-loading feedback.
5. **P3 — `$impeccable polish`:** R14 and final typography/spacing consistency, after the core journey and deployment acceptance priorities in PLAN.md.

These commands describe possible follow-up scopes; the missing Impeccable engine need not block manual implementation. They can be requested separately or together. This review does not authorize a new product direction or reprioritize pending release gates.

After fixes, rerun the failing foundation suite plus focused checks for dirty navigation, errors in closed disclosures, background failures, long content, company filter history and appended-result announcements. Include 320/375/768/1440px, keyboard-only use, actual zoom, reduced motion and at least one screen-reader journey. Keep Vite/browser validation isolated from frontend mutations and other Vite/Vitest/build processes. Re-run `$impeccable audit` when its engine is available; retain manual checks for issues axe misses. These are future acceptance scenarios, not passed checks.
