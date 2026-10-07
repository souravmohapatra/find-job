# Development examples

Updated: 2026-10-07. These employers exercise discovery, collection and browsing during development. They are not a production watchlist, a profession-specific product default, or hardcoded matching logic. Only load an optional development seed into isolated test data; never auto-subscribe a real profile.

## Company set

Netflix, Spotify, Amazon, Revolut and Airwallex come from the user; additional examples broaden the requested categories. Categories describe the development coverage, not an assumption about each employer's available jobs.

| Category | Company | Public starting point | Origin |
| --- | --- | --- | --- |
| Entertainment | Netflix | [Careers](https://explore.jobs.netflix.net/careers) | User example |
| Entertainment | Spotify | [Jobs](https://www.lifeatspotify.com/jobs) | User example |
| Entertainment | Disney | [Careers](https://www.disneycareers.com/en) | Additional example |
| Finance/payments | Revolut | [Careers](https://www.revolut.com/careers/) | User example |
| Finance/payments | Airwallex | [Careers](https://careers.airwallex.com/) | User example |
| Finance/payments | Wise | [Careers](https://wise.jobs/) | Additional example |
| General corporate strategy context | Amazon | [Jobs](https://www.amazon.jobs/en/) | User example |
| General corporate strategy context | Microsoft | [Careers](https://careers.microsoft.com/v2/global/en/home.html) | Additional example |
| Consulting | BCG | [Careers](https://careers.bcg.com/global/en/) | Additional example |
| Consulting | Accenture | [Careers](https://www.accenture.com/gb-en/careers) | Additional example |

Public entry points were located/read on 2026-10-07. This is not evidence of working adapters, complete job counts, current strategy vacancies, or permission to access restricted endpoints. Verify actual source structure during development rather than assuming these companies use the initially selected ATS APIs. Do not interpret an unrendered “0 jobs” placeholder as a successful empty inventory.

The named-company development pass should record discovery identity, source type, whether HTTP or rendering is needed, pagination/coverage limits, and observed failures. Test all five user-named examples; use additions to broaden coverage. If a named company cannot yet be collected, document that gap instead of claiming support based on a career URL. Prioritize generic/custom-source work when the observed mix warrants it; do not specialize matching for these employers.

## Missing careers page and offline fixtures

Use a fictional employer on a controlled fixture site with no careers link, and fixture search results leading to verified and misleading third-party job pages. This tests missing-source discovery without falsely labelling a named employer as lacking a careers page. Include an unresolved-company and a blocked-source fixture.

Use small synthetic snapshots for repeatable automated tests and bounded live checks during development. Never scrape live employers on every unit-test run. Production onboarding starts with no monitored companies.

## Broad-shortlist examples

These are synthetic descriptions for the illustrative strategy-consulting profile, not assertions about live vacancies. Core function and evidence matter more than title keywords.

| Example responsibilities | Expected result |
| --- | --- |
| Corporate strategy: market sizing, business cases and executive recommendations, in a familiar sector | Shortlist |
| Strategy and operations in a new sector, some transferable commercial/problem-solving work, many unfamiliar requirements | Shortlist at the broad threshold |
| Commercial strategy with only roughly one-third of relevant experience demonstrated | Shortlist; gaps explained |
| Transformation consulting, seniority stretch and missing salary | Shortlist as possible unless the owner explicitly sets a conflicting must-have |
| Strategy analyst whose main output is strategic recommendations and planning | Shortlist; do not reject the word analyst |
| Data analyst whose main output is SQL reporting, dashboards and data pipelines | Exclude from strategy shortlist; retain in All jobs |
| Legal counsel requiring legal practice and primary responsibility for contracts/litigation | Exclude from strategy shortlist; shared finance/entertainment context does not rescue it |
| Mixed or underspecified business role with credible strategy responsibilities but uncertain details | Shortlist for manual review |

Repeat the function-boundary test with a synthetic data-professional or legal-professional profile to prove those functions are not globally blacklisted. No precision optimization campaign or elaborate ranking benchmark is needed for v1.
