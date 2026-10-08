# Progress and complexity review

Review date: 2026-10-08.

This is a read-only architectural assessment of the project at the time of review, recorded at the user's request. It compares the original product intent with the current plan, progress record, Compose configuration, source structure and sampled implementations. It is not a full correctness or security audit. Tests were not rerun, and recorded validation results were not independently reproduced. Recommendations below are proposals, not approved changes to requirements or implementation scope.

## Overall assessment

The progress is real and generally disciplined, but the project is becoming heavier than a one-person job finder needs for its first usable release. There is some premature engineering. The bigger concern is how much has been built before proving the core benefit with real jobs.

This is a promising, carefully built application whose ambition is getting ahead of its demonstrated usefulness. The recommended response is to narrow the next acceptance milestone, not rewrite the application or add more architecture.

## Complexity that is justified

The requirements in [CONTEXT.md](CONTEXT.md) are more demanding than a daily scraping script: editable CV analysis, different company websites, broad explainable matching, persistent scheduling, private deployment and notifications. Some complexity follows directly from those requirements.

Several decisions look sound:

- Keeping collected jobs independent of matching protects manual browsing.
- Distinguishing collection failures from “no vacancies” prevents misleading results.
- Tracking profile changes prevents outdated assessments appearing current.
- PostgreSQL plus a database-backed queue avoids adding Redis or another broker.
- Fetch isolation has a concrete purpose: external websites should not reach private services.
- Authentication, bounded spending, backups and basic retry protection are reasonable even for one owner.

The progress record carefully distinguishes synthetic checks, real local database/browser tests and unverified live behaviour. That is good engineering practice. See [PLAN.md](PLAN.md) and [PROGRESS.md](PROGRESS.md).

## Areas of disproportionate or premature complexity

| Area | Assessment |
| --- | --- |
| Background execution | The application maintains its own operation states, leases, retries and recovery alongside Procrastinate's queue machinery. There are valid transactional reasons, but this is a substantial maintenance burden for the expected workload. |
| Provider accounting | Spending limits are useful. Detailed reservation recovery, billing reconciliation and dedicated recovery UI feel advanced before any live model has been accepted. |
| Extraction breadth | ATS adapters, JSON-LD, AI extraction, configurable CSS rules, previews and planned browser fallback collectively approach a general-purpose collection platform. Broader website support is required eventually, but the first release could prove a narrower path. |
| Recovery and configuration UI | Conflict handling and explicit errors are useful. Completing many advanced controls before observing actual usage increases the chance of polishing workflows the owner rarely needs. |
| Deployment | Ten Compose services and six networks are substantial for personal hosting. However, two services are one-shot setup jobs and several share an image, so describing this as ten independent microservices would be unfair. |

The most concrete simplification candidate is the interaction between [operation handling](backend/app/services/operations.py) and [queue dispatch/recovery](backend/app/tasks/worker.py). Review that boundary before adding more lifecycle states; do not remove existing recovery guarantees without understanding their purpose.

At inspection, the backend contained approximately 9,300 application lines across 63 Python files, excluding tests. Size alone does not establish overengineering, but this has become a meaningful application to maintain.

Other sampled implementation evidence includes [provider integration](backend/app/ai/provider.py), [matching policy](backend/app/domain/matching.py), [notification delivery](backend/app/notifications/delivery.py) and [Compose topology](compose.yaml). Sampling does not establish that every mechanism is necessary or correct.

## The strongest concern: order of work

The application has extensive local validation, but the decisive product questions remain open:

- Does it reliably collect the jobs the owner actually cares about?
- Does the chosen model produce a useful broad shortlist?
- Does the scheduled digest reach the owner's device?
- Can the owner install and operate it on the intended server?

Those questions could change the design more than another recovery screen or frontend optimisation.

The user deliberately deferred live model selection and paid validation, and the development network blocked other acceptance work. The agent was right to respect those boundaries and continue independent tasks. However, continuing to build peripheral features indefinitely is not necessarily the best response to blocked validation.

Much of this complexity was already selected in [IMPLEMENTATION.md](IMPLEMENTATION.md). This is partly an ambitious-plan problem, not simply an agent wandering outside scope. [DECISIONS.md](DECISIONS.md) distinguishes user requirements from selected implementation defaults; the latter remain candidates for reassessment.

## Recommended next milestone

Keep the existing work and make the next acceptance milestone smaller:

1. Freeze new capabilities and optional polish.
2. Complete a basic backup/restore path.
3. On the intended host, prove one complete journey: reviewed profile → real collection → real matching → portal → scheduled ntfy delivery.
4. Start with a few representative companies, including one difficult source; then expand to the agreed development examples.
5. Use observed failures to choose the next engineering work.

Live paid checks still require the user's authorization and model choices. Advanced features can remain implemented without making their further refinement mandatory for the first usable milestone. A narrower milestone does not silently remove the existing requirements or deployment acceptance gates.

The priority should be getting the application to help the owner find real jobs before investing further in sophistication.
