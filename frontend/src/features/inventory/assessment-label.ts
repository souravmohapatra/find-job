import type { Schemas } from './data';
const verdicts = { match: 'Relevant', possible_match: 'Possible', not_match: 'Not a match' };
export function assessmentLabel(job: Schemas['JobView']) {
  if (job.assessment) return verdicts[job.assessment.category];
  const state = job.assessment_operation?.state;
  const progress =
    state === 'running'
      ? 'Assessing'
      : state === 'queued'
        ? 'Assessment queued'
        : state === 'blocked'
          ? 'Assessment needs attention'
          : state === 'failed'
            ? 'Assessment failed'
            : 'Not assessed';
  return job.assessment_status === 'stale' ? `Outdated assessment · ${progress}` : progress;
}
