import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test, vi } from 'vitest';
import { App } from '../src/app/app';
import { api, ApiError } from '../src/lib/api';
const session = { username: 'owner', csrf_token: 'synthetic-csrf-token' };
const clients: QueryClient[] = [];
function renderApp(path = '/jobs') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
  vi.unstubAllGlobals();
});
function respond(data: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
test('login preserves the requested route and logout sends CSRF then clears private cache', async () => {
  const user = userEvent.setup();
  let signedIn = false;
  const fetch = vi.fn(async (input: string, init?: RequestInit) => {
    if (input.endsWith('/auth/me'))
      return signedIn
        ? respond(session)
        : respond({ code: 'unauthenticated', message: 'Sign in.' }, 401);
    if (input.endsWith('/auth/login')) {
      expect(JSON.parse(String(init?.body))).toEqual({
        username: 'owner',
        password: 'synthetic-password',
      });
      signedIn = true;
      return respond(session);
    }
    if (input.endsWith('/auth/logout')) {
      expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe(session.csrf_token);
      signedIn = false;
      return respond(null, 204);
    }
    throw new Error('Unexpected request');
  });
  vi.stubGlobal('fetch', fetch);
  const client = renderApp('/companies');
  await user.type(await screen.findByLabelText('Username'), 'owner');
  await user.type(screen.getByLabelText('Password'), 'synthetic-password');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  await screen.findByRole('heading', { name: 'Companies', level: 1 });
  client.setQueryData(['private-jobs'], [{ title: 'Synthetic role' }]);
  await user.click(screen.getByRole('button', { name: 'Sign out' }));
  await screen.findByRole('button', { name: 'Sign in' });
  expect(client.getQueryData(['private-jobs'])).toBeUndefined();
  expect(localStorage.length).toBe(0);
});
test('failed login preserves input, exposes an actionable error, and does not reveal password', async () => {
  vi.spyOn(api, 'session').mockResolvedValue(null);
  vi.spyOn(api, 'login').mockRejectedValue(
    new ApiError(401, 'invalid_credentials', 'Username or password is incorrect.'),
  );
  const user = userEvent.setup();
  renderApp();
  await user.type(await screen.findByLabelText('Username'), 'owner');
  await user.type(screen.getByLabelText('Password'), 'wrong-password');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('Username or password is incorrect.');
  expect(screen.getByLabelText('Username')).toHaveValue('owner');
  expect(screen.getByLabelText('Password')).toHaveValue('wrong-password');
  expect(alert).not.toHaveTextContent('wrong-password');
  await waitFor(() => expect(alert).toHaveFocus());
});
test('session service failure is recoverable and is not presented as signed out', async () => {
  const sessionCall = vi
    .spyOn(api, 'session')
    .mockRejectedValueOnce(
      new ApiError(503, 'database_unavailable', 'Storage is temporarily unavailable.'),
    )
    .mockResolvedValueOnce(null);
  const user = userEvent.setup();
  renderApp();
  expect(await screen.findByRole('alert')).toHaveTextContent('Storage is temporarily unavailable.');
  expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Try again' }));
  await screen.findByLabelText('Username');
  expect(sessionCall).toHaveBeenCalledTimes(2);
});
test('empty form validates locally and password visibility is keyboard-operable', async () => {
  vi.spyOn(api, 'session').mockResolvedValue(null);
  const login = vi.spyOn(api, 'login');
  const user = userEvent.setup();
  renderApp();
  await user.click(await screen.findByRole('button', { name: 'Sign in' }));
  expect(login).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Username')).toHaveAttribute('aria-invalid', 'true');
  await user.click(screen.getByRole('button', { name: 'Show password' }));
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'text');
  await user.click(screen.getByRole('button', { name: 'Hide password' }));
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
});

test('session expiry removes private cached data and returns to sign-in', async () => {
  vi.spyOn(api, 'session').mockResolvedValueOnce(session).mockResolvedValueOnce(null);
  const client = renderApp();
  await screen.findByRole('heading', { name: 'A wider view of what’s next' });
  client.setQueryData(['private-profile'], { summary: 'Synthetic experience' });
  await act(async () => {
    await client.invalidateQueries({ queryKey: ['session'] });
  });
  await screen.findByLabelText('Username');
  expect(client.getQueryData(['private-profile'])).toBeUndefined();
});

test('failed sign-out keeps the workspace visible and reports the failure', async () => {
  vi.spyOn(api, 'session').mockResolvedValue(session);
  vi.spyOn(api, 'logout').mockRejectedValue(
    new ApiError(0, 'network_error', 'Cannot reach Job Finder.'),
  );
  const user = userEvent.setup();
  renderApp();
  await user.click(await screen.findByRole('button', { name: 'Sign out' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach Job Finder.');
  expect(screen.getByRole('heading', { name: 'A wider view of what’s next' })).toBeVisible();
});
