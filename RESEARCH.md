# Existing-tool research

Source: public web research during the initial discussion on 2026-10-07. These are documentation-level candidates, not installed, audited, or tested foundations. Recheck capabilities, licences, and maintenance before choosing or copying code.

| Candidate | Documented relevance | Evaluation gap |
| --- | --- | --- |
| [HeadStart](https://github.com/davidcristian/HeadStart) | Self-hosted platform advertising web configuration, polling, deduplication, notifications, AI summaries, and Docker Compose. | Verify actual coverage, CV-derived preference flow, diversification, local ntfy extensibility, and complexity. |
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io) | Docker deployment, web page monitoring, filtering, and browser fetching. | Primarily page-change monitoring; company discovery and structured job/profile assessment need evaluation or another layer. |
| [job-alerts](https://github.com/SirFuzzyWalls/job-alerts) | Scheduled recruitment-platform collection, title filters, email digest, and supported-platform probing. | Configuration/CLI-oriented; portal, generic profile analysis, and ntfy need investigation. |
| [JobOps](https://github.com/DaKheera47/job-ops) | Docker deployment, job search/scoring, application tooling, and company watchlist features described in releases. | Broader scope than this product; examine reuse cost and its stated AGPLv3 + Commons Clause terms. |

ntfy explicitly documents changedetection.io integration: [official example](https://docs.ntfy.sh/examples/#changedetectionio). JobOps watchlist evidence: [releases](https://github.com/DaKheera47/job-ops/releases).

## Proposed comparison

Start with HeadStart as the closest advertised overall fit and changedetection.io as a simpler monitoring reference. Compare generic profile customization, all-jobs preservation, discovery for missing careers pages, domain diversification, failure visibility, and notification integration. This was the initial shortlist; the implementation decision below supersedes the undecided foundation status.

Use representative sources and synthetic candidate data in a later authorized evaluation. A project README is not execution evidence. Do not infer full company coverage from a list of supported recruitment platforms.

## Implementation-stage conclusion — 2026-10-07

Choose a new focused application using established libraries, rather than a complete platform fork. This is a scope/ownership tradeoff from public documentation review; it does not establish that the alternatives are defective or unusable.

A refreshed [HeadStart README](https://github.com/davidcristian/HeadStart) explicitly lists ntfy, generic browser adapters, and local AI, correcting our earlier uncertainty about whether notification support would need adding. It also includes auto-application, mailbox workflows, subscriptions, and identifies its licence as SSPL. [JobOps](https://github.com/DaKheera47/job-ops) similarly covers a larger application workflow and labels its licence AGPLv3 + Commons Clause. We do not need to inherit those workflows for this product. No code has been copied from either project.

changedetection.io remains a useful reference for page-change monitoring, but the central data in this app is a structured job inventory plus versioned profile assessments. Keeping another monitoring platform in the runtime would add integration state, so it is not a selected dependency. Individual library licences and any future copied adapters must still be checked before reuse.

Technical choices are supported by official references linked directly in IMPLEMENTATION.md, SOURCES.md, MATCHING.md and DEPLOYMENT.md. Repository features and upstream documentation were reviewed, but no candidate was installed or benchmarked.
