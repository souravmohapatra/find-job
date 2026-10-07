import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import { BillingHistory } from '../src/features/settings/billing';
import type { components } from '../src/lib/api-types';
import * as api from '../src/lib/api';

const call: components['schemas']['CallView'] = {
  id: '00000000-0000-4000-8000-000000000001',
  task: 'profile_analysis',
  operation_id: null,
  state: 'unknown',
  model: 'example/synthetic',
  provider: null,
  generation_id: null,
  reserved_usd: '0.56',
  reported_usd: null,
  cost_source: null,
  accounted_at: null,
  error_code: 'ai_cost_unknown',
  created_at: '2026-10-07T10:00:00Z',
};

test('billing verification requires a confirmed amount, preserves failed input and never retries AI', async () => {
  const request = vi
    .spyOn(api, 'request')
    .mockRejectedValueOnce(
      new api.ApiError(503, 'unavailable', 'Accounting is temporarily unavailable.'),
    )
    .mockResolvedValueOnce({ ...call, state: 'owner_reconciled' });
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <BillingHistory
        usage={{ day_start_utc: call.created_at, tasks: [], recent: [call], unresolved: [call] }}
        names={{ profile_analysis: 'CV analysis' }}
        csrf="synthetic"
        live={false}
      />
    </QueryClientProvider>,
  );
  expect(screen.getByText(/No generation ID was received/)).toBeVisible();
  await user.click(screen.getByText('Record a charge you verified'));
  const button = screen.getByRole('button', { name: 'Record verified cost' });
  expect(button).toBeDisabled();
  const amount = screen.getByLabelText('Verified cost (USD)');
  await user.type(amount, '0.25');
  expect(button).toBeDisabled();
  await user.click(screen.getByLabelText('I checked this request in provider billing'));
  await user.click(button);
  const error = await screen.findByRole('alert');
  await waitFor(() => expect(error).toHaveFocus());
  expect(amount).toHaveValue(0.25);
  expect(screen.getByLabelText('I checked this request in provider billing')).toBeChecked();
  await user.click(button);
  expect(await screen.findByRole('status')).toHaveTextContent('No AI retry was started');
  expect(request).toHaveBeenCalledTimes(2);
  for (const [path, options, csrf] of request.mock.calls) {
    expect(path).toBe(`/settings/ai/usage/${call.id}/verify`);
    expect(JSON.parse(options!.body as string)).toEqual({
      cost_usd: '0.25',
      confirmation: 'I VERIFIED THE PROVIDER BILLING',
    });
    expect(csrf).toBe('synthetic');
  }
  client.clear();
});
