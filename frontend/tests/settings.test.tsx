import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import { AiSettings } from '../src/features/settings/ai';
import type { components } from '../src/lib/api-types';
import * as api from '../src/lib/api';

test('AI configuration conflicts preserve model choices and make no validation request', async () => {
  const settings: components['schemas']['AiSettingsView'] = {
    integration_mode: 'mock',
    key_configured: false,
    limits_revision: 0,
    limits: { daily_calls: 500, daily_usd: '5' },
    tasks: [
      {
        task: 'profile_analysis',
        revision: 1,
        validation_state: 'unvalidated',
        error_code: null,
        config: {
          model: 'example/old',
          zdr: false,
          fallback_models: [],
          providers: [],
          input_tokens: 16000,
          output_tokens: 4000,
          timeout_seconds: 120,
          prompt_price: '20',
          completion_price: '60',
          request_price: '0',
        },
      },
    ],
  };
  const request = vi.spyOn(api, 'request').mockImplementation(async (path, options) => {
    if (options?.method === 'PATCH')
      throw new api.ApiError(409, 'revision_conflict', 'Settings changed elsewhere.');
    if (path === '/settings/ai/usage') return { tasks: [] };
    return settings;
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(['session'], { username: 'owner', csrf_token: 'synthetic' });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <AiSettings />
    </QueryClientProvider>,
  );
  const input = await screen.findByLabelText('Model ID');
  await user.clear(input);
  await user.type(input, 'example/new');
  await user.click(screen.getByLabelText('Use only zero data retention endpoints'));
  await user.click(screen.getByRole('button', { name: 'Save cv analysis' }));
  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('Settings changed elsewhere');
  await waitFor(() => expect(alert).toHaveFocus());
  expect(input).toHaveValue('example/new');
  expect(screen.getByLabelText('Use only zero data retention endpoints')).toBeChecked();
  expect(request.mock.calls.some(([path]) => path.endsWith('/validate'))).toBe(false);
  // A background refresh must not replace unsaved values with someone else's revision.
  client.setQueryData(['ai-settings'], {
    ...settings,
    tasks: [{ ...settings.tasks[0], revision: 2 }],
  });
  await waitFor(() => expect(screen.getByText(/A newer configuration is available/)).toBeVisible());
  expect(input).toHaveValue('example/new');
  expect(within(alert).queryByRole('button')).toBeNull();
  client.clear();
});
