import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import { ProfileEditor } from '../src/features/profile/editor';
import { profileApi, type Snapshot } from '../src/features/profile/api';
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
