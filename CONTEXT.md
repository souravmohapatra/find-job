# Product context

Updated: 2026-10-07. Source: initial product discussion and subsequent authorization to decide and document implementation details.

## Intent

Reduce the repeated effort of checking selected companies for suitable vacancies. The user supplies companies and a CV; the app maintains a customizable profile, collects job listings on a schedule, assesses fit, and notifies the user. All collected vacancies remain available for manual inspection.

## Confirmed requirements

- Upload a CV and use AI to understand experience, job history, role types, skills, domains, and years of experience.
- Save the extracted profile and job preferences in an editable setup/profile page.
- Start with one active profile; keep the analyzer and application logic generic across professions and industries.
- Initial illustrative user: a strategy consultant with finance and entertainment expertise, interested in both familiar and new domains. This is context, not a built-in persona or an uploaded CV.
- Offer an explicit option to diversify target domains.
- Accept companies with or without an existing careers page, retain monitoring requests, and check daily or at a custom interval.
- Collect new available listings and use AI to assess them against the saved profile/preferences. The selected structured rubric and deterministic category policy are in MATCHING.md.
- Offer a company-level view of all collected jobs regardless of matching filters.
- Provide a polished, minimalist web portal.
- Run Docker Compose on an Ubuntu Server with local ntfy, exposed only over the LAN and local tailnet, with no public access.
- Research adapting existing tools before deciding whether to build from scratch.
- Use OpenRouter API for LLM work, with different configurable models for different tasks. Exact models will be decided later; no local LLM is required.
- Cast a wide net: roughly 30% relevance is enough for a shortlist, with manual review. Avoid clearly unrelated primary functions (e.g. data-analysis or legal-practice roles for a strategy target); do not optimize high-precision ranking.
- Send one configurable daily summary, default 19:00 in the selected timezone. Daily or twice-daily collection is independent of digest timing.
- Netflix, Spotify, Amazon, Revolut and Airwallex, plus similar entertainment/finance/strategy/consulting employers, are development examples only, not production defaults.

## Product distinctions

CV-derived facts describe past experience; preferences describe future intent. A candidate may want to move beyond the industries in their CV. User corrections take precedence over inferred profile details.

Domain diversification concerns suitability across industries within monitored sources. Automatically discovering additional companies is a separate possible capability and is not yet agreed.

“All jobs” means all listings successfully collected from the company's configured/discovered sources. It is not a guarantee of complete market coverage. Source coverage and failures must be visible.

A job's first discovery time is distinct from its advertised publication date. An empty successful check, an unresolved source, and a failed check are different outcomes.

## Scope boundary

The initial high-level plan has been extended into implementation design at the user's request. Technical decisions and defaults are now recorded; application implementation is now authorized and underway. Current execution evidence and blockers are recorded in PROGRESS.md and VALIDATION.md. Automatic application submission, CV rewriting, application tracking, multiple active profiles, OCR, and automatic company recommendations are outside v1.
