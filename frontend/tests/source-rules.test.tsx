import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import { SourceRules } from '../src/features/inventory/source-rules';
import type { Schemas } from '../src/features/inventory/data';
import * as api from '../src/lib/api';

const rules: Schemas['SelectorRules'] = {
  employer_scope: 'card',
  cards: '.job',
  title: 'h2',
  link: 'a',
  description: '.description',
  employer: '.employer',
};
const source: Schemas['SourceView'] = {
  id: 'source',
  company_id: 'company',
  adapter: 'generic_http',
  url: 'https://example.com/jobs',
  enabled: false,
  authoritative: false,
  interval_hours: 24,
  revision: 1,
  next_due_at: '2026-10-07T12:00:00Z',
  baseline_at: null,
  last_error: null,
  last_success_at: null,
  cooldown_until: null,
  rules,
};
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
  client.setQueryData(['session'], { username: 'owner', csrf_token: 'synthetic' });
  client.setQueryData(['sources', 'company'], [source]);
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper, user: userEvent.setup() };
}

test('preview is invalidated by edits and save clears rules only with explicit automatic selection', async () => {
  const request = vi.spyOn(api, 'request').mockImplementation(async (_path, options) =>
    options?.method === 'POST'
      ? {
          accepted_jobs: 1,
          complete: true,
          fetched_at: '2026-10-07T12:00:00Z',
          examples: ['Strategy manager'],
          issues: [],
        }
      : { ...source, revision: 2, rules: null },
  );
  const { client, wrapper, user } = setup();
  render(<SourceRules source={source} />, { wrapper });
  await user.click(screen.getByText('Website extraction rules (advanced)'));
  await user.click(screen.getByRole('button', { name: 'Preview saved page' }));
  expect(await screen.findByText('Strategy manager')).toBeVisible();
  await user.type(screen.getByLabelText('Job title'), '.title');
  expect(screen.queryByText('Strategy manager')).toBeNull();
  await user.click(screen.getByLabelText('Use custom extraction rules'));
  await user.click(screen.getByRole('button', { name: 'Save extraction rules' }));
  expect(await screen.findByText(/Extraction rules saved/)).toBeVisible();
  const call = request.mock.calls.find(([, options]) => options?.method === 'PUT');
  expect(JSON.parse(call?.[1]?.body as string)).toEqual({ rules: null });
  client.clear();
  request.mockRestore();
});

test('background changes retain edits and conflict review requires an explicit revision choice', async () => {
  let puts = 0;
  const saved = { ...source, revision: 2, rules: { ...rules, title: '.saved' } };
  const request = vi.spyOn(api, 'request').mockImplementation(async (_path, options) => {
    if (options?.method === 'PUT') {
      if (++puts === 1) throw new api.ApiError(409, 'revision_conflict', 'Source changed.');
      return { ...saved, revision: 3 };
    }
    return [saved];
  });
  const { client, wrapper, user } = setup();
  const view = render(<SourceRules source={source} />, { wrapper });
  await user.click(screen.getByText('Website extraction rules (advanced)'));
  await user.clear(screen.getByLabelText('Job title'));
  await user.type(screen.getByLabelText('Job title'), '.mine');
  view.rerender(<SourceRules source={saved} />);
  expect(screen.getByLabelText('Job title')).toHaveValue('.mine');
  await user.click(screen.getByRole('button', { name: 'Save extraction rules' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveFocus());
  await user.click(screen.getByRole('button', { name: 'Compare saved rules' }));
  expect(await screen.findByText('.saved')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Keep my draft for review' }));
  expect(puts).toBe(1);
  await user.click(screen.getByRole('button', { name: 'Save extraction rules' }));
  await screen.findByText(/Extraction rules saved/);
  const call = request.mock.calls.filter(([, options]) => options?.method === 'PUT').at(-1);
  expect(call?.[1]?.headers).toEqual({ 'If-Match': '"2"' });
  expect(JSON.parse(call?.[1]?.body as string).rules.title).toBe('.mine');
  client.clear();
  request.mockRestore();
});
