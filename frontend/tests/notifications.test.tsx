import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import { NotificationSettings } from '../src/features/settings/notifications';
import type { components } from '../src/lib/api-types';
import * as api from '../src/lib/api';

type S = components['schemas'];
const settings: S['NotificationSettingsView'] = {
  revision: 1,
  enabled: true,
  timezone: 'Europe/London',
  local_time: '19:00',
  include_empty: true,
  next_date: '2026-10-08',
  next_due_at: '2026-10-08T18:00:00Z',
  delivery_mode: 'mock',
  publisher_configured: false,
};
const digest: S['DigestView'] = {
  id: 'digest-one',
  content_removed: false,
  local_date: '2026-10-07',
  cutoff: '2026-10-07T18:00:00Z',
  timezone: 'Europe/London',
  local_time: '19:00',
  integration_mode: 'mock',
  state: 'unknown',
  created_at: '2026-10-07T18:00:00Z',
  snapshot: {
    counts: { new: 2, baseline: 1, reassessment: 0 },
    companies: {},
    examples: [],
    source_errors: 0,
    pending_operations: 0,
    assessment_errors: 0,
    unresolved_companies: 0,
    matching_available: true,
  },
  delivery: {
    id: 'delivery-one',
    attempt: 1,
    batch_attempt: 1,
    manual: false,
    deadline_at: '2026-10-07T18:30:00Z',
    state: 'unknown',
    retryable: false,
    error_code: 'ntfy_delivery_unknown',
    remote_id: null,
    available_at: '2026-10-07T18:01:00Z',
    started_at: '2026-10-07T18:00:00Z',
    finished_at: '2026-10-07T18:00:10Z',
  },
};
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(['session'], { username: 'owner', csrf_token: 'synthetic' });
  render(
    <QueryClientProvider client={client}>
      <NotificationSettings />
    </QueryClientProvider>,
  );
  return client;
}
function reads(path: string, rows: S['DigestView'][] = []) {
  if (path === '/settings/notifications') return settings;
  if (path === '/settings/notifications/tests') return [];
  if (path === '/notifications') return { items: rows, next_before: null };
  throw new Error('Unexpected request: ' + path);
}

test('notification schedule conflict preserves edits and original revision', async () => {
  let current = settings;
  const request = vi.spyOn(api, 'request').mockImplementation(async (path, options) => {
    if (options?.method === 'PATCH')
      throw new api.ApiError(409, 'revision_conflict', 'Schedule changed elsewhere.');
    return path === '/settings/notifications' ? current : reads(path);
  });
  const client = mount();
  const user = userEvent.setup();
  const zone = await screen.findByLabelText('Timezone');
  await user.clear(zone);
  await user.type(zone, 'Asia/Kolkata');
  await user.click(screen.getByRole('button', { name: 'Save notification schedule' }));
  const error = await screen.findByRole('alert');
  await waitFor(() => expect(error).toHaveFocus());
  current = { ...settings, revision: 2, timezone: 'UTC' };
  client.setQueryData(['notification-settings'], current);
  await screen.findByText(/A newer schedule is available/);
  expect(zone).toHaveValue('Asia/Kolkata');
  await user.click(screen.getByRole('button', { name: 'Save notification schedule' }));
  expect(
    request.mock.calls
      .filter(([, options]) => options?.method === 'PATCH')
      .every(([, options]) => (options?.headers as Record<string, string>)['If-Match'] === '"1"'),
  ).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Discard edits and reload schedule' }));
  expect(zone).toHaveValue('UTC');
  client.clear();
});

test('test notification keeps its request key after an ambiguous network error', async () => {
  let calls = 0;
  const request = vi.spyOn(api, 'request').mockImplementation(async (path, options) => {
    if (options?.method === 'POST') {
      if (++calls === 1) throw new api.ApiError(0, 'network_error', 'Connection lost.');
      return { operation_id: 'op', resource_id: 'delivery', status_url: '/op' };
    }
    return reads(path);
  });
  const client = mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Test notification' }));
  await screen.findByText('Connection lost.');
  await user.click(screen.getByRole('button', { name: 'Retry test request' }));
  await screen.findByText('Test queued. Its result appears below.');
  const posts = request.mock.calls.filter(([, options]) => options?.method === 'POST');
  expect(posts).toHaveLength(2);
  expect(posts[0][1]?.headers).toEqual(posts[1][1]?.headers);
  client.clear();
});

test('unknown resend requires acknowledgement and replays the same body after network loss', async () => {
  let calls = 0;
  const request = vi.spyOn(api, 'request').mockImplementation(async (path, options) => {
    if (options?.method === 'POST') {
      if (++calls === 1) throw new api.ApiError(0, 'network_error', 'Connection lost.');
      return { operation_id: 'op', resource_id: 'delivery', status_url: '/op' };
    }
    return reads(path, [digest]);
  });
  const client = mount();
  const user = userEvent.setup();
  await user.click(await screen.findByText('Delivery history'));
  const button = await screen.findByRole('button', { name: 'Resend summary' });
  expect(button).toBeDisabled();
  await user.click(
    screen.getByLabelText('I understand that resending may deliver this summary twice.'),
  );
  await user.click(button);
  await screen.findByText('Connection lost.');
  await user.click(screen.getByRole('button', { name: 'Retry resend request' }));
  await screen.findByText('Resend queued.');
  const posts = request.mock.calls.filter(([, options]) => options?.method === 'POST');
  expect(posts).toHaveLength(2);
  expect(posts[0][1]).toEqual(posts[1][1]);
  expect(JSON.parse(posts[0][1]?.body as string)).toEqual({
    expected_delivery_id: 'delivery-one',
    accept_possible_duplicate: true,
  });
  client.clear();
});

test('purged content is not shown as zero results or offered for resend', async () => {
  vi.spyOn(api, 'request').mockImplementation(async (path) =>
    reads(path, [
      {
        ...digest,
        content_removed: true,
        snapshot: {
          ...digest.snapshot,
          counts: { new: 0, baseline: 0, reassessment: 0 },
          matching_available: false,
        },
        delivery: { ...digest.delivery!, state: 'failed' },
      },
    ]),
  );
  const client = mount();
  const user = userEvent.setup();
  await user.click(await screen.findByText('Delivery history'));
  await screen.findByText('Summary content removed with profile data.');
  expect(screen.queryByRole('button', { name: 'Resend summary' })).toBeNull();
  expect(screen.queryByText(/0 new roles/)).toBeNull();
  expect(screen.getByText(/Delivery unknown: an earlier send may have arrived/)).toBeVisible();
  client.clear();
});
