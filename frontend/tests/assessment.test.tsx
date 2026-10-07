import { assessmentLabel } from '../src/features/inventory/assessment-label';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { expect, test, vi } from 'vitest';
import { AssessmentPanel, FeedbackPanel } from '../src/features/inventory/assessment';
import type { Schemas } from '../src/features/inventory/data';
import * as api from '../src/lib/api';

const job: Schemas['JobDetail'] = {
  id: 'job',
  company_id: 'company',
  company_label: 'Example',
  revision_id: 'revision',
  revision: 1,
  availability: 'active',
  baseline: false,
  first_seen_at: '2026-10-07T12:00:00Z',
  last_seen_at: '2026-10-07T12:00:00Z',
  posting: {
    external_id: 'one',
    title: 'Strategy role',
    description: 'Lead strategy',
    url: 'https://example.com/job',
    apply_url: 'https://example.com/job',
  },
  sources: [],
  revision_count: 1,
  assessment_status: 'not_assessed',
};
function wrap(
  child: React.ReactNode,
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  }),
) {
  client.setQueryData(['session'], { username: 'owner', csrf_token: 'synthetic' });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{child}</MemoryRouter>
    </QueryClientProvider>
  );
}
test('feedback requires a choice and keeps dirty text and version through refresh and conflict', async () => {
  const user = userEvent.setup();
  const request = vi
    .spyOn(api, 'request')
    .mockRejectedValue(new api.ApiError(409, 'feedback_conflict', 'Feedback changed elsewhere.'));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(wrap(<FeedbackPanel job={job} />, client));
  await user.type(screen.getByLabelText('Reason (optional)'), 'Keep my note');
  expect(screen.getByRole('button', { name: 'Save feedback' })).toBeDisabled();
  await user.click(screen.getByRole('radio', { name: 'Not relevant' }));
  view.rerender(
    wrap(
      <FeedbackPanel
        job={{
          ...job,
          feedback: {
            value: 'relevant',
            reason: 'Saved elsewhere',
            revision: 1,
            updated_at: job.first_seen_at,
          },
        }}
      />,
      client,
    ),
  );
  expect(screen.getByLabelText('Reason (optional)')).toHaveValue('Keep my note');
  await user.click(screen.getByRole('button', { name: 'Save feedback' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveFocus());
  expect(screen.getByLabelText('Reason (optional)')).toHaveValue('Keep my note');
  const payload = JSON.parse(request.mock.calls[0][1]?.body as string);
  expect(payload).toEqual({ value: 'not_relevant', reason: 'Keep my note', expected_revision: 0 });
  expect(
    screen.getByRole('button', { name: 'Discard edits and load saved feedback' }),
  ).toBeVisible();
});
test('possible match presents mock provenance and inspectable evidence without unsafe markup', async () => {
  const user = userEvent.setup();
  const evidence = [
    { span_id: 'job:description', quote: 'Lead strategy <script>not executable</script>' },
  ];
  const assessed: Schemas['JobDetail'] = {
    ...job,
    assessment_status: 'assessed',
    assessment: {
      id: 'assessment',
      profile_revision_id: 'profile',
      config_id: 'config',
      policy_version: 'broad-v1',
      integration_mode: 'mock',
      category: 'possible_match',
      created_at: job.first_seen_at,
      report: {
        primary_function: 'Strategy',
        relation: 'adjacent',
        function_evidence: evidence,
        relevance_score: 30,
        plausible_connection: true,
        domain_status: 'unknown',
        important_unknowns: true,
        reasons: [{ text: 'Transferable planning experience', evidence }],
      },
    },
  };
  render(wrap(<AssessmentPanel job={assessed} />));
  expect(screen.getByText('Possible', { exact: true })).toBeVisible();
  expect(screen.getByText(/Mock result for development/)).toBeVisible();
  await user.click(screen.getByText('Supporting evidence'));
  expect(screen.getAllByText('Lead strategy <script>not executable</script>')[0]).toBeVisible();
  expect(document.querySelector('script')).toBeNull();
  expect(
    screen.queryByRole('button', { name: 'Assess with current preferences' }),
  ).not.toBeInTheDocument();
});
test('failed assessment remains unassessed and its retry uses authenticated mutation', async () => {
  const user = userEvent.setup();
  const request = vi.spyOn(api, 'request').mockResolvedValue({ operation_id: 'op' });
  const failed: Schemas['JobDetail'] = {
    ...job,
    assessment_operation: {
      id: 'op',
      kind: 'job_assess',
      state: 'failed',
      attempts: 3,
      progress: 'Failed',
      error_code: 'synthetic',
      error_message: 'Synthetic provider error',
      created_at: job.first_seen_at,
      finished_at: job.first_seen_at,
    },
  };
  expect(assessmentLabel(failed)).toBe('Assessment failed');
  render(wrap(<AssessmentPanel job={failed} />));
  expect(screen.getByText('Synthetic provider error')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Assess with current preferences' }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      '/jobs/job/reassess',
      { method: 'POST', headers: { 'Idempotency-Key': expect.any(String) } },
      'synthetic',
    ),
  );
});

test('uncertain reassessment requests retain the same replay key', async () => {
  const user = userEvent.setup();
  const request = vi
    .spyOn(api, 'request')
    .mockRejectedValueOnce(new api.ApiError(0, 'network_error', 'Connection lost.'))
    .mockResolvedValue({ operation_id: 'op' });
  render(wrap(<AssessmentPanel job={job} />));
  await user.click(screen.getByRole('button', { name: 'Assess with current preferences' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveFocus());
  await user.click(screen.getByRole('button', { name: 'Assess with current preferences' }));
  await screen.findByText('Assessment requested.');
  expect(request.mock.calls).toHaveLength(2);
  expect(request.mock.calls[0][1]?.headers).toEqual(request.mock.calls[1][1]?.headers);
});
