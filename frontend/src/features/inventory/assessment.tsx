import { useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Button } from '../../components/ui/button';
import { ApiError, request } from '../../lib/api';
import { date, read, useCsrf, type Schemas } from './data';
import { Failure } from './shared';

import { assessmentLabel } from './assessment-label';

function Evidence({ items }: { items: Schemas['Evidence'][] }) {
  return (
    <ul>
      {items.map((item, i) => (
        <li key={i}>
          <span className="field-help">
            {item.span_id.startsWith('job:')
              ? 'Listing'
              : item.span_id.startsWith('profile:')
                ? 'Reviewed profile'
                : 'Your preferences'}
            :{' '}
          </span>
          <q>{item.quote}</q>
        </li>
      ))}
    </ul>
  );
}
export function AssessmentPanel({ job }: { job: Schemas['JobDetail'] }) {
  const client = useQueryClient();
  const csrf = useCsrf();
  const requestKey = useRef<string | null>(null);
  const action = useMutation({
    mutationFn: () => {
      requestKey.current ??= crypto.randomUUID();
      return request(
        `/jobs/${job.id}/reassess`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': requestKey.current },
        },
        csrf,
      );
    },
    onSuccess: async () => {
      requestKey.current = null;
      await client.invalidateQueries({ queryKey: ['job', job.id] });
      await client.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
  const result = job.assessment;
  const report = result?.report;
  const active = ['queued', 'running'].includes(job.assessment_operation?.state ?? '');
  return (
    <section className="panel assessment-panel">
      <h2>Assessment</h2>
      <p>
        <strong>{assessmentLabel(job)}</strong>
        {result?.integration_mode === 'mock' && ' · Mock result for development'}
      </p>
      {report ? (
        <>
          <p>
            Primary function: {report.primary_function} · {report.relation}
          </p>
          <p className="field-help">
            {report.relevance_score == null
              ? 'Relevance is uncertain.'
              : `Broad relevance: ${report.relevance_score}/100.`}{' '}
            This is a guide for review, not a hiring probability.
          </p>
          {report.important_unknowns && (
            <p>Important details are unknown. Review the gaps before deciding.</p>
          )}
          {(['reasons', 'transferable', 'gaps'] as const).map((field) =>
            report[field]?.length ? (
              <div key={field}>
                <h3>
                  {field === 'reasons'
                    ? 'Why consider this role'
                    : field === 'transferable'
                      ? 'Transferable experience'
                      : 'Gaps and unknowns'}
                </h3>
                <ul>
                  {report[field].map((reason, i) => (
                    <li key={i}>
                      <p>{reason.text}</p>
                      <details>
                        <summary>Supporting evidence</summary>
                        <Evidence items={reason.evidence} />
                      </details>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null,
          )}
          {Boolean(report.criteria?.length) && (
            <div>
              <h3>Your criteria</h3>
              <ul>
                {report.criteria!.map((criterion) => (
                  <li key={criterion.preference_id}>
                    <p>
                      {criterion.status.replaceAll('_', ' ')} · {criterion.explanation}
                    </p>
                    {Boolean(criterion.evidence?.length) && (
                      <details>
                        <summary>Supporting evidence</summary>
                        <Evidence items={criterion.evidence!} />
                      </details>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <details>
            <summary>How this was assessed</summary>
            <p>
              Assessed {date(result.created_at)} against your saved profile and preferences. Domain
              evidence: {report.domain_status.replaceAll('_', ' ')}.
            </p>
            <h3>Primary duties and role fit</h3>
            <Evidence items={report.function_evidence} />
            {Boolean(report.score_evidence?.length) && (
              <>
                <h3>Relevance evidence</h3>
                <Evidence items={report.score_evidence!} />
              </>
            )}
          </details>
        </>
      ) : (
        <>
          <p>
            {job.assessment_status === 'stale'
              ? 'The listing, profile or matching settings changed. An up-to-date assessment is needed.'
              : 'This role has no current assessment. You can still review the full listing.'}
          </p>
          {job.assessment_operation?.error_message && (
            <p role="status">{job.assessment_operation.error_message}</p>
          )}
          <p>
            <Link to="/profile">Review profile</Link> ·{' '}
            <Link to="/settings">Matching settings</Link>
          </p>
          <Button disabled={active || action.isPending || !csrf} onClick={() => action.mutate()}>
            {action.isPending
              ? 'Requesting assessment…'
              : active
                ? 'Assessment in progress'
                : 'Assess with current preferences'}
          </Button>
          {action.isSuccess && <p role="status">Assessment requested.</p>}
          {action.isError && <Failure error={action.error} focus />}
        </>
      )}
    </section>
  );
}
export function FeedbackPanel({ job }: { job: Schemas['JobDetail'] }) {
  const client = useQueryClient();
  const csrf = useCsrf();
  const [draft, setDraft] = useState<
    | (Omit<Schemas['FeedbackInput'], 'value'> & { value: Schemas['FeedbackInput']['value'] | '' })
    | null
  >(null);
  const values = draft ?? {
    value: job.feedback?.value ?? '',
    reason: job.feedback?.reason ?? '',
    expected_revision: job.feedback?.revision ?? 0,
  };
  const save = useMutation({
    mutationFn: () =>
      request(
        `/jobs/${job.id}/feedback`,
        { method: 'PUT', body: JSON.stringify(values) },
        csrf,
      ) as Promise<Schemas['FeedbackView']>,
    onSuccess: (feedback) => {
      client.setQueryData(['job', job.id], { ...job, feedback });
      setDraft(null);
    },
  });
  const reload = useMutation({
    mutationFn: () => read<Schemas['JobDetail']>(`/jobs/${job.id}`),
    onSuccess: (fresh) => {
      client.setQueryData(['job', job.id], fresh);
      setDraft(null);
      save.reset();
    },
  });
  return (
    <section className="panel">
      <h2>Your feedback</h2>
      <p className="field-help">
        Record your view for later review. This does not change your preferences or the AI
        shortlist.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <fieldset disabled={save.isPending || reload.isPending}>
          <legend>Is this role relevant to you?</legend>
          {(['relevant', 'not_relevant'] as const).map((value) => (
            <label className="check-label" key={value}>
              <input
                type="radio"
                name="relevance-feedback"
                value={value}
                checked={(draft?.value ?? job.feedback?.value) === value}
                onChange={() => {
                  save.reset();
                  setDraft({ ...values, value });
                }}
              />
              {value === 'relevant' ? 'Relevant' : 'Not relevant'}
            </label>
          ))}
          <div className="field">
            <label htmlFor="feedback-reason">Reason (optional)</label>
            <textarea
              id="feedback-reason"
              maxLength={2000}
              value={values.reason ?? ''}
              onChange={(event) => {
                save.reset();
                setDraft({ ...values, reason: event.target.value });
              }}
            />
          </div>
          <Button type="submit" disabled={!draft || !values.value || !csrf}>
            Save feedback
          </Button>
        </fieldset>
      </form>
      {save.isSuccess && <p role="status">Feedback saved.</p>}
      {save.isError && <Failure error={save.error} focus />}
      {save.error instanceof ApiError && save.error.code === 'feedback_conflict' && (
        <Button variant="secondary" disabled={reload.isPending} onClick={() => reload.mutate()}>
          Discard edits and load saved feedback
        </Button>
      )}
      {reload.isError && <Failure error={reload.error} focus />}
    </section>
  );
}
