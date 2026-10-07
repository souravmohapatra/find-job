import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import { DiscoveryHistory } from '../src/features/inventory/discovery';
import * as api from '../src/lib/api';

const company = {
  id: 'company',
  label: 'Example Studio',
  interval_hours: 24,
  paused: false,
  revision: 1,
  resolution: 'needs_review',
  coverage: {
    collected_jobs: 0,
    active_jobs: 0,
    unknown_jobs: 0,
    closed_jobs: 0,
    sources: 0,
    enabled_sources: 0,
    partial_sources: 0,
    sources_needing_attention: 0,
    sources_without_success: 0,
  },
  created_at: '2026-10-07T12:00:00Z',
};
const history = [
  {
    id: 'run',
    company_revision: 1,
    state: 'partial',
    cursor: 1,
    issues: ['search_candidates_unverified'],
    started_at: '2026-10-07T12:00:00Z',
    finished_at: '2026-10-07T12:00:01Z',
    candidates: [
      {
        url: 'https://example.com/careers',
        title: 'Example careers',
        employer: null,
        source_url: 'https://example.com/careers',
        evidence_path: 'brave.web.results',
        status: 'needs_identity_review',
      },
    ],
  },
];

test('candidate confirmation is explicit and conflict preserves the selected page', async () => {
  const request = vi.spyOn(api, 'request').mockImplementation(async (_path, options) => {
    if (options?.method === 'POST')
      throw new api.ApiError(409, 'revision_conflict', 'Company changed elsewhere.');
    return history;
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(['session'], { username: 'owner', csrf_token: 'synthetic' });
  const onOperation = vi.fn();
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <DiscoveryHistory company={company} onOperation={onOperation} />
    </QueryClientProvider>,
  );
  expect(await screen.findByText('Search result · company identity unverified')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Confirm company page' })).toBeNull();
  await user.click(screen.getByRole('radio'));
  expect(screen.getByRole('button', { name: 'Confirm company page' })).toBeDisabled();
  await user.click(
    screen.getByLabelText('I checked that the selected page belongs to Example Studio'),
  );
  await user.click(screen.getByRole('button', { name: 'Confirm company page' }));
  const alert = await screen.findByRole('alert');
  await waitFor(() => expect(alert).toHaveFocus());
  expect(screen.getByRole('radio')).toBeChecked();
  expect(screen.getByRole('checkbox')).toBeChecked();
  expect(onOperation).not.toHaveBeenCalled();
  const call = request.mock.calls.find(([, options]) => options?.method === 'POST');
  expect(call?.[1]?.headers).toEqual({ 'If-Match': '"1"' });
  expect(JSON.parse(call?.[1]?.body as string)).toEqual({
    url: 'https://example.com/careers',
    confirmed_company: true,
  });
  client.clear();
  request.mockRestore();
});

test('old discovery candidates remain inspectable but cannot be selected', async () => {
  const request = vi.spyOn(api, 'request').mockResolvedValue(history);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(['session'], { username: 'owner', csrf_token: 'synthetic' });
  render(
    <QueryClientProvider client={client}>
      <DiscoveryHistory company={{ ...company, revision: 2 }} onOperation={() => {}} />
    </QueryClientProvider>,
  );
  expect(await screen.findByRole('link', { name: 'Example careers' })).toHaveAttribute(
    'href',
    'https://example.com/careers',
  );
  expect(screen.queryByRole('radio')).toBeNull();
  client.clear();
  request.mockRestore();
});
