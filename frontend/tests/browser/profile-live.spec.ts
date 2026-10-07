import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test('real upload → worker parsing → review → saved preferences', async ({ page }) => {
  await page.goto('/profile');
  await page.getByLabel('Username').fill('owner');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(
    page.getByText(
      'Development mode: local parsing with mock analysis. No AI request will be made.',
    ),
  ).toBeVisible();
  await page.getByLabel('CV file').setInputFiles({
    name: 'synthetic-designer.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(
      'Synthetic product designer\nExample studio, 2020-2024\nDesigned accessible services and led discovery workshops.',
    ),
  });
  await page.getByRole('button', { name: 'Upload and analyse' }).click();
  await expect(page.getByLabel('Professional summary')).toBeVisible({ timeout: 90_000 });
  await expect(page.getByLabel('Professional summary')).toHaveValue('Synthetic product designer');
  await page
    .getByLabel('Desired roles or functions — one per line')
    .fill('Product design\nService design');
  await expect(page.getByRole('radio', { name: 'Open to any domain' })).toBeChecked();
  await page.getByRole('radio', { name: 'Prefer selected domains, explore others' }).check();
  await page.getByLabel('Selected domains — one per line').fill('Education\nTransport');
  await page.getByRole('button', { name: 'Add role', exact: true }).click();
  await page.getByLabel('Company or organisation').fill('Example studio');
  await page.getByLabel('Role title', { exact: true }).fill('Product designer');
  await page.getByLabel('Start date').fill('2020-01');
  await page.getByLabel('End date').fill('2024-01');
  await page.getByText('Location, seniority and other criteria', { exact: true }).click();
  await page.getByRole('button', { name: 'Add preference', exact: true }).click();
  await page.getByLabel('What would you like?').fill('Flexible working hours');
  await page.getByLabel('I have reviewed my experience and preferences.').check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/profile-${width}.png`, fullPage: true });
  }
  await page.getByRole('button', { name: 'Approve profile' }).click();
  await expect(page.getByRole('heading', { name: 'Your reviewed profile' })).toBeVisible();
  await expect(page.getByText('Product design, Service design', { exact: true })).toBeVisible();
  await expect(page.getByText('Prefer Education, Transport', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Prefer Education, Transport', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit profile' }).click();
  await page.getByRole('radio', { name: 'Open to any domain' }).check();
  await page.getByLabel('I have reviewed my experience and preferences.').check();
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByText('Open to any domain', { exact: true })).toBeVisible();
  const profile = await page.request.get('/api/v1/profile');
  const data = await profile.json();
  expect(data.revision).toBe(2);
  expect(data.preferences.criteria[0].strength).toBe('preferred');
  expect(data.preferences.relevance_threshold).toBe(30);
});

test('real model settings → reload → explicit mock validation', async ({ page }) => {
  await page.goto('/settings');
  await page.getByLabel('Username').fill('owner');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  const task = page
    .locator('.ai-task')
    .filter({ has: page.getByRole('heading', { name: 'CV analysis', exact: true }) });
  await task.getByLabel('Model ID', { exact: true }).fill('example/synthetic');
  await task.getByLabel('Use only zero data retention endpoints').check();
  await task.getByRole('button', { name: 'Save cv analysis' }).click();
  await expect(task.getByText('Model settings saved.')).toBeVisible();
  await expect(task.getByRole('button', { name: 'Check mock configuration' })).toBeEnabled();
  await page.reload();
  await expect(task.getByLabel('Model ID', { exact: true })).toHaveValue('example/synthetic');
  await expect(task.getByLabel('Use only zero data retention endpoints')).toBeChecked();
  await task.getByRole('button', { name: 'Check mock configuration' }).click();
  await expect(
    task.getByText('Mock configuration checked. No provider request was made.'),
  ).toBeVisible({ timeout: 90000 });
  await page.getByLabel('Estimated spend per day (USD)').fill('3');
  await page.getByRole('button', { name: 'Save daily limits' }).click();
  await expect(page.getByText('Daily limits saved.')).toBeVisible();
  await task.getByText('Advanced model settings', { exact: true }).click();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/settings-${width}.png`, fullPage: true });
  }
  const settings = await (await page.request.get('/api/v1/settings/ai')).json();
  expect(settings.tasks[0].validation_state).toBe('mock_only');
  expect(settings.tasks[0].config.temperature).toBeNull();
  expect(settings.tasks[1].config.model).toBeNull();
  expect(Number(settings.limits.daily_usd)).toBe(3);
  const usage = await (await page.request.get('/api/v1/settings/ai/usage')).json();
  expect(usage.tasks.every((task: { calls_today: number }) => task.calls_today === 0)).toBe(true);
});

test('CV retention, original removal and explicit profile purge', async ({ page }) => {
  await page.goto('/profile');
  await page.getByLabel('Username').fill('owner');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByLabel('CV file')).toBeVisible();
  const session = await (await page.request.get('/api/v1/auth/me')).json();
  const headers = { Origin: 'http://127.0.0.1:5173', 'X-CSRF-Token': session.csrf_token };
  const before = await (await page.request.get('/api/v1/profile')).json();
  const create = await page.request.patch('/api/v1/profile', {
    headers: { ...headers, 'If-Match': `"${before.revision}"` },
    data: {
      facts: { summary: 'Synthetic teacher for deletion test' },
      preferences: { desired_roles: ['Teaching'] },
    },
  });
  expect(create.ok()).toBe(true);
  const uploaded = await page.request.post('/api/v1/profile/documents', {
    headers,
    multipart: {
      file: {
        name: 'synthetic-teacher.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('Synthetic teacher\nTaught science'),
      },
    },
  });
  const document = await uploaded.json();
  expect(uploaded.status()).toBe(202);
  await page.reload();
  await page.getByText('CV storage and profile data', { exact: true }).click();
  const row = page.locator('.document-list li').first();
  await row.getByLabel('Keep this original until I delete it').check();
  await expect(row.getByLabel('Keep this original until I delete it')).toBeEnabled();
  await page.reload();
  await page.getByText('CV storage and profile data', { exact: true }).click();
  await expect(row.getByLabel('Keep this original until I delete it')).toBeChecked();
  await row.getByRole('button', { name: 'Remove original', exact: true }).click();
  await row.getByRole('button', { name: 'Confirm removal' }).click();
  await expect(row.getByText('Original file and raw text removed.')).toBeVisible();
  expect(
    (await page.request.get(`/api/v1/profile/documents/${document.resource_id}/download`)).status(),
  ).toBe(404);
  await expect(
    page.getByText('Synthetic teacher for deletion test', { exact: true }),
  ).toBeVisible();
  await page.getByText('Delete profile and all CV data', { exact: true }).click();
  await expect(page.getByRole('button', { name: 'Delete profile and CVs' })).toBeDisabled();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/profile-data-${width}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  }
  await page.getByLabel('Type DELETE PROFILE to confirm').fill('DELETE PROFILE');
  await page.getByRole('button', { name: 'Delete profile and CVs' }).click();
  await expect(page.getByRole('heading', { name: 'Your reviewed profile' })).not.toBeVisible();
  const after = await (await page.request.get('/api/v1/profile')).json();
  expect(after.revision_id).toBeNull();
  expect(after.drafts).toEqual([]);
  expect((await (await page.request.get('/api/v1/profile/documents')).json()).documents).toEqual(
    [],
  );
});
