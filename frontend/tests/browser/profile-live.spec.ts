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
