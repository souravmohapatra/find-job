import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { expect, test, vi } from 'vitest';
import { JobList } from '../src/features/inventory/jobs';
import * as api from '../src/lib/api';

function renderList(
  path: string,
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <JobList companyId="owned-company" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

test('company scope survives clear filters and cannot be replaced by URL company_id', async () => {
  const request = vi
    .spyOn(api, 'request')
    .mockResolvedValue({ items: [], next_cursor: null, matching_available: true });
  const client = renderList(
    '/companies/owned-company?view=all&company_id=other-company&q=Legal&availability=closed',
  );
  await screen.findByText('No collected jobs in this view');
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Clear filters' }));
  await waitFor(() => expect(screen.getByLabelText('Availability')).toHaveValue('open'));
  await waitFor(() =>
    expect(
      request.mock.calls.some(
        ([path]) => path === '/jobs?view=all&availability=open&company_id=owned-company',
      ),
    ).toBe(true),
  );
  expect(request.mock.calls.every(([path]) => path.includes('company_id=owned-company'))).toBe(
    true,
  );
  expect(screen.getByLabelText('Search collected jobs')).toHaveValue('');
  client.clear();
  request.mockRestore();
});

test('missing matching model offers all jobs without presenting an empty shortlist', async () => {
  const request = vi.spyOn(api, 'request').mockImplementation(async (path) => {
    if (path.includes('view=recommended'))
      throw new api.ApiError(503, 'matching_unavailable', 'Choose a model');
    return { items: [], next_cursor: null, matching_available: false };
  });
  const client = renderList('/companies/owned-company');
  const action = await screen.findByRole('button', { name: 'Browse all collected jobs' });
  expect(screen.queryByText('No current shortlist entries in this view')).toBeNull();
  await userEvent.setup().click(action);
  expect(await screen.findByText('No collected jobs in this view')).toBeVisible();
  expect(request.mock.calls.at(-1)?.[0]).toContain('company_id=owned-company');
  client.clear();
  request.mockRestore();
});

test('a newly unavailable model hides cached shortlist entries after revalidation', async () => {
  const request = vi
    .spyOn(api, 'request')
    .mockRejectedValue(new api.ApiError(503, 'matching_unavailable', 'Choose a model'));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(['jobs', 'view=recommended&availability=open&company_id=owned-company'], {
    pageParams: [''],
    pages: [
      {
        next_cursor: null,
        matching_available: true,
        items: [
          {
            id: 'old',
            company_label: 'Example',
            availability: 'active',
            first_seen_at: '2026-10-07T12:00:00Z',
            posting: { title: 'Old shortlisted role' },
            assessment_status: 'not_assessed',
          },
        ],
      },
    ],
  });
  renderList('/companies/owned-company', client);
  await screen.findByRole('button', { name: 'Browse all collected jobs' });
  expect(screen.queryByRole('link', { name: 'Old shortlisted role' })).toBeNull();
  client.clear();
  request.mockRestore();
});
