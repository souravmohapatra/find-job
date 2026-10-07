import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import { ProfileEditor } from '../src/features/profile/editor';
import { profileApi, type Draft, type Snapshot } from '../src/features/profile/api';
import { ApiError } from '../src/lib/api';
const initial: Snapshot = {
  revision: 1,
  revision_id: '00000000-0000-4000-8000-000000000001',
  facts: { summary: 'Reviewed synthetic researcher' },
  preferences: {
    desired_roles: ['Research'],
    domain_mode: 'open',
    goals: '',
    relevance_threshold: 30,
  },
  experience: null,
};
test('a conflicting save retains edits, diversification and the focused error', async () => {
  const save = vi
    .spyOn(profileApi, 'save')
    .mockRejectedValue(new ApiError(409, 'revision_conflict', 'This profile changed elsewhere.'));
  const onSaved = vi.fn();
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <ProfileEditor initial={initial} csrf="synthetic-token" onSaved={onSaved} />
    </QueryClientProvider>,
  );
  await user.clear(screen.getByLabelText('Professional summary'));
  await user.type(screen.getByLabelText('Professional summary'), 'My edited experience');
  await user.click(screen.getByRole('radio', { name: 'Prefer selected domains, explore others' }));
  await user.type(screen.getByLabelText('Selected domains — one per line'), 'Education');
  await user.click(screen.getByLabelText('I have reviewed my experience and preferences.'));
  await user.click(screen.getByRole('button', { name: 'Save profile' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('This profile changed elsewhere.');
  await waitFor(() => expect(screen.getByRole('alert')).toHaveFocus());
  expect(screen.getByLabelText('Professional summary')).toHaveValue('My edited experience');
  expect(screen.getByLabelText('Selected domains — one per line')).toHaveValue('Education');
  expect(onSaved).not.toHaveBeenCalled();
  expect(save.mock.calls[0][0]).toBe(1);
  expect(save.mock.calls[0][1].preferences.domain_mode).toBe('expand');
  client.clear();
});

test('background refresh preserves edits and explicit comparison adopts chosen saved fields', async () => {
  const latest: Snapshot = {
    ...initial,
    revision: 2,
    facts: { summary: 'Remote summary' },
    preferences: { ...initial.preferences, goals: 'Work in education' },
  };
  const save = vi
    .spyOn(profileApi, 'save')
    .mockRejectedValueOnce(
      new ApiError(409, 'revision_conflict', 'This profile changed elsewhere.'),
    )
    .mockResolvedValueOnce({ ...latest, revision: 3 });
  vi.spyOn(profileApi, 'profile').mockResolvedValue({ ...latest, drafts: [] });
  const onSaved = vi.fn();
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const user = userEvent.setup();
  const view = render(
    <QueryClientProvider client={client}>
      <ProfileEditor initial={initial} csrf="synthetic-token" onSaved={onSaved} />
    </QueryClientProvider>,
  );
  await user.clear(screen.getByLabelText('Professional summary'));
  await user.type(screen.getByLabelText('Professional summary'), 'My local summary');
  // Simulate a query refresh delivering a newer snapshot to the same editor.
  view.rerender(
    <QueryClientProvider client={client}>
      <ProfileEditor initial={latest} csrf="synthetic-token" onSaved={onSaved} />
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText('Professional summary')).toHaveValue('My local summary');
  await user.click(screen.getByLabelText('I have reviewed my experience and preferences.'));
  await user.click(screen.getByRole('button', { name: 'Save profile' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('This profile changed elsewhere');
  expect(save.mock.calls[0][0]).toBe(1);
  await user.click(screen.getByRole('button', { name: 'Compare saved changes' }));
  await screen.findByRole('heading', { name: 'Reconcile saved changes' });
  expect(screen.getByRole('button', { name: 'Continue with these choices' })).toBeDisabled();
  await user.click(screen.getByLabelText('Keep my summary'));
  await user.click(screen.getByLabelText('Use saved profile goals'));
  await user.click(screen.getByLabelText('I have compared these changes'));
  await user.click(screen.getByRole('button', { name: 'Continue with these choices' }));
  await waitFor(() =>
    expect(
      screen.queryByRole('heading', { name: 'Reconcile saved changes' }),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getByLabelText('Professional summary')).toHaveValue('My local summary');
  expect(screen.getByLabelText('Anything else about your next role?')).toHaveValue(
    'Work in education',
  );
  expect(screen.getByRole('button', { name: 'Save profile' })).toBeDisabled();
  await user.click(screen.getByLabelText('I have reviewed my experience and preferences.'));
  await user.click(screen.getByRole('button', { name: 'Save profile' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  expect(save.mock.calls[1][0]).toBe(2);
  expect(save.mock.calls[1][1].facts.summary).toBe('My local summary');
  expect(save.mock.calls[1][1].preferences.goals).toBe('Work in education');
  client.clear();
});

test('draft conflict reconciles both revisions and does not reuse another CV evidence', async () => {
  const draft: Draft = {
    document_available: true,
    id: '00000000-0000-4000-8000-000000000010',
    document_id: '00000000-0000-4000-8000-000000000011',
    operation_id: null,
    status: 'review',
    version: 1,
    base_revision: 1,
    base_profile: initial,
    spans: [{ id: 's1', text: 'New CV summary' }],
    facts: {
      summary: 'New CV summary',
      summary_evidence: [{ span_id: 's1', quote: 'New CV summary' }],
    },
    preferences: initial.preferences,
  };
  const latest = {
    ...initial,
    revision: 2,
    facts: {
      summary: 'Approved elsewhere',
      summary_evidence: [{ span_id: 's1', quote: 'Different old CV text' }],
    },
    preferences: { ...initial.preferences, goals: 'Education' },
  };
  const latestDraft = { ...draft, version: 3, facts: { summary: 'Someone edited this draft' } };
  const reconciled = {
    ...latestDraft,
    version: 4,
    base_revision: 2,
    facts: { summary: 'Approved elsewhere', summary_evidence: [] },
    preferences: latest.preferences,
    base_profile: latest,
  };
  const save = vi
    .spyOn(profileApi, 'saveDraft')
    .mockRejectedValueOnce(new ApiError(409, 'revision_conflict', 'This draft changed elsewhere.'))
    .mockResolvedValueOnce({ ...reconciled, version: 5 });
  vi.spyOn(profileApi, 'profile').mockResolvedValue({ ...latest, drafts: [] });
  vi.spyOn(profileApi, 'draft').mockResolvedValue(latestDraft);
  const reconcile = vi.spyOn(profileApi, 'reconcile').mockResolvedValue(reconciled);
  const activate = vi.spyOn(profileApi, 'activate').mockResolvedValue({ ...latest, revision: 3 });
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <ProfileEditor initial={draft} draft={draft} csrf="synthetic-token" onSaved={vi.fn()} />
    </QueryClientProvider>,
  );
  await user.click(screen.getByLabelText('I have reviewed my experience and preferences.'));
  await user.click(screen.getByRole('button', { name: 'Approve profile' }));
  await user.click(await screen.findByRole('button', { name: 'Compare saved changes' }));
  await user.click(await screen.findByLabelText('Use saved profile summary'));
  await user.click(screen.getByLabelText('Use saved profile goals'));
  await user.click(screen.getByLabelText('I have compared these changes'));
  await user.click(screen.getByRole('button', { name: 'Continue with these choices' }));
  await waitFor(() => expect(reconcile).toHaveBeenCalledOnce());
  expect(reconcile.mock.calls[0].slice(0, 3)).toEqual([draft.id, 3, 2]);
  expect(reconcile.mock.calls[0][3].facts.summary_evidence).toEqual([]);
  expect(activate).not.toHaveBeenCalled();
  await waitFor(() =>
    expect(
      screen.queryByRole('heading', { name: 'Reconcile saved changes' }),
    ).not.toBeInTheDocument(),
  );
  await user.click(screen.getByLabelText('I have reviewed my experience and preferences.'));
  await user.click(screen.getByRole('button', { name: 'Approve profile' }));
  await waitFor(() => expect(activate).toHaveBeenCalledWith(draft.id, 5, 2, 'synthetic-token'));
  expect(save.mock.calls[1][1]).toBe(4);
  client.clear();
});
