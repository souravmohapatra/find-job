import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
for (const width of [375, 768, 1440]) {
  test(`sign-in and navigation at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    let signedIn = false;
    await page.route('**/api/v1/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      const session = { username: 'owner', csrf_token: 'browser-test-csrf' };
      if (path.endsWith('/auth/me'))
        return route.fulfill({
          status: signedIn ? 200 : 401,
          json: signedIn ? session : { code: 'unauthenticated', message: 'Sign in.' },
        });
      if (path.endsWith('/auth/login')) {
        signedIn = true;
        return route.fulfill({ json: session });
      }
      if (path.endsWith('/auth/logout')) {
        expect(route.request().headers()['x-csrf-token']).toBe(session.csrf_token);
        signedIn = false;
        return route.fulfill({ status: 204 });
      }
      if (path.endsWith('/status'))
        return route.fulfill({
          json: {
            environment: 'test',
            integration_mode: 'mock',
            profile_configured: false,
            phase: 'foundation',
          },
        });
      if (path.endsWith('/companies'))
        return route.fulfill({ json: { items: [], next_offset: null } });
      if (path.endsWith('/jobs'))
        return route.fulfill({
          status: 503,
          json: {
            code: 'matching_unavailable',
            message: 'Shortlisting is not available yet. Browse all collected jobs.',
          },
        });
      if (path.endsWith('/settings/ai/usage'))
        return route.fulfill({
          json: { tasks: [], recent: [], unresolved: [], day_start_utc: '2026-10-07T00:00:00Z' },
        });
      if (path.endsWith('/settings/ai'))
        return route.fulfill({
          json: {
            integration_mode: 'mock',
            key_configured: false,
            limits_revision: 0,
            limits: { daily_calls: 500, daily_usd: '5' },
            tasks: [],
          },
        });
      throw new Error(`Unexpected API request: ${path}`);
    });
    await page.goto('/companies');
    await expect(page.getByLabel('Username')).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.getByLabel('Username').fill('owner');
    await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('heading', { name: 'Companies', exact: true })).toBeVisible();
    await page.getByRole('link', { name: 'Jobs', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Jobs', exact: true })).toBeFocused();
    await expect(page.getByRole('navigation')).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/workspace-${width}.png`, fullPage: true });
    await page.getByRole('link', { name: 'Settings', exact: true }).click();
    await expect(page.getByText('Mock responses for development')).toBeVisible();
    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByLabel('Username')).toBeVisible();
  });
}
