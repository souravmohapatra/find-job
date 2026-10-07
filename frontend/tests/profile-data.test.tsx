import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import { ProfileData } from '../src/features/profile/data';
import * as api from '../src/lib/api';

test('failed retention change rolls back the toggle and keeps profile data', async () => {
  let rejectSave: (error: Error) => void = () => {};
  vi.spyOn(api, 'request').mockImplementation(async (_path, options) => {
    if (options?.method === 'PATCH')
      return new Promise((_resolve, reject) => {
        rejectSave = reject;
      });
    return {
      next_offset: null,
      documents: [
        {
          id: 'synthetic-document',
          media_type: 'text/plain',
          size: 20,
          status: 'queued',
          retain_original: false,
          created_at: '2026-01-01T00:00:00Z',
          approved_at: null,
          deleted_at: null,
        },
      ],
    };
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(['profile-draft', 'synthetic'], {
    facts: { summary: 'Synthetic saved draft' },
  });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <ProfileData csrf="synthetic" onPurged={vi.fn()} />
    </QueryClientProvider>,
  );
  await user.click(screen.getByText('CV storage and profile data'));
  const checkbox = await screen.findByLabelText('Keep this original until I delete it');
  await user.click(checkbox);
  expect(checkbox).toBeChecked();
  expect(checkbox).toBeDisabled();
  act(() => rejectSave(new api.ApiError(503, 'unavailable', 'Storage temporarily unavailable.')));
  expect(await screen.findByRole('alert')).toHaveTextContent('Storage temporarily unavailable');
  await waitFor(() => expect(checkbox).not.toBeChecked());
  expect(checkbox).toBeEnabled();
  expect(client.getQueryData(['profile-draft', 'synthetic'])).toEqual({
    facts: { summary: 'Synthetic saved draft' },
  });
  client.clear();
});
