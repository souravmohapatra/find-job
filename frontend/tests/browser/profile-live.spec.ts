import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
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

test('profile conflict preserves local edits and reconciles selected saved values', async ({
  page,
}) => {
  await page.goto('/profile');
  await page.getByLabel('Username').fill('owner');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByLabel('CV file')).toBeVisible();
  const session = await (await page.request.get('/api/v1/auth/me')).json();
  const headers = { Origin: 'http://127.0.0.1:5173', 'X-CSRF-Token': session.csrf_token };
  const existing = await (await page.request.get('/api/v1/profile')).json();
  const original = {
    facts: { summary: 'Synthetic researcher' },
    preferences: { desired_roles: ['Research'], domain_mode: 'open', goals: '' },
  };
  const seeded = await page.request.patch('/api/v1/profile', {
    headers: { ...headers, 'If-Match': `"${existing.revision}"` },
    data: original,
  });
  expect(seeded.ok()).toBe(true);
  const seed = await seeded.json();
  await page.reload();
  await page.getByRole('button', { name: 'Edit profile', exact: true }).click();
  await page.getByLabel('Professional summary').fill('My local research summary');
  const remote = await page.request.patch('/api/v1/profile', {
    headers: { ...headers, 'If-Match': `"${seed.revision}"` },
    data: {
      ...original,
      facts: { summary: 'Remote research summary' },
      preferences: { ...original.preferences, goals: 'Work in education' },
    },
  });
  expect(remote.ok()).toBe(true);
  await page.getByLabel('I have reviewed my experience and preferences.').check();
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('changed elsewhere');
  await expect(page.getByLabel('Professional summary')).toHaveValue('My local research summary');
  await page.getByRole('button', { name: 'Compare saved changes' }).click();
  await expect(page.getByRole('heading', { name: 'Reconcile saved changes' })).toBeVisible();
  await page.getByLabel('Keep my summary', { exact: true }).check();
  await page.getByLabel('Use saved profile goals', { exact: true }).check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `test-results/profile-conflict-${width}.png`, fullPage: true });
  }
  await page.getByLabel('I have compared these changes').check();
  await page.getByRole('button', { name: 'Continue with these choices' }).click();
  await expect(page.getByRole('heading', { name: 'Reconcile saved changes' })).not.toBeVisible();
  await expect(page.getByLabel('Anything else about your next role?')).toHaveValue(
    'Work in education',
  );
  await expect(page.getByRole('button', { name: 'Save profile', exact: true })).toBeDisabled();
  await page.getByLabel('I have reviewed my experience and preferences.').check();
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your reviewed profile' })).toBeVisible();
  const result = await (await page.request.get('/api/v1/profile')).json();
  expect(result.revision).toBe(seed.revision + 2);
  expect(result.facts.summary).toBe('My local research summary');
  expect(result.preferences.goals).toBe('Work in education');
});

test('real billing recovery records verified cost without a new AI request', async ({ page }) => {
  const id = execFileSync('../backend/.venv/bin/python', ['../scripts/seed-browser-billing.py'], {
    encoding: 'utf8',
  }).trim();
  await page.goto('/settings');
  await page.getByLabel('Username').fill('owner');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(
    page.getByText('No generation ID was received, so automatic lookup is unavailable.'),
  ).toBeVisible();
  await page.getByText('Record a charge you verified').click();
  const submit = page.getByRole('button', { name: 'Record verified cost' });
  await expect(submit).toBeDisabled();
  await page.getByLabel('Verified cost (USD)').fill('0.25');
  await expect(submit).toBeDisabled();
  await page.getByLabel('I checked this request in provider billing').check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/billing-${width}.png`, fullPage: true });
  }
  await submit.click();
  await expect(page.getByText(/Verified charge recorded. No AI retry was started/)).toBeVisible();
  await expect(page.getByLabel('Verified cost (USD)')).toHaveCount(0);
  const response = await page.request.get('/api/v1/settings/ai/usage');
  expect(response.ok()).toBe(true);
  const usage = await response.json();
  expect(usage.unresolved).toEqual([]);
  const call = usage.recent.find((entry: { id: string }) => entry.id === id);
  expect(call.cost_source).toBe('owner_verified');
  expect(Number(call.reported_usd)).toBe(0.25);
  expect(usage.recent).toHaveLength(1);
});

test('company watch → source controls → all jobs → detail and retained filters', async ({
  page,
}) => {
  await page.goto('/companies');
  await page.getByLabel('Username').fill('owner');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByLabel('Company name', { exact: true }).fill('Synthetic Entertainment');
  await page.getByLabel('Check interval (hours)').fill('12');
  await page.getByRole('button', { name: 'Follow company' }).click();
  await expect(
    page.getByRole('heading', { name: 'Synthetic Entertainment', exact: true }),
  ).toBeVisible();
  const companyId = new URL(page.url()).pathname.split('/').at(-1)!;
  await expect(
    page.getByText('No source configured yet. Your company watch is retained.'),
  ).toBeVisible();
  await page.getByLabel('Job board provider').selectOption('lever');
  await page.getByLabel('Board identifier').fill('synthetic');
  await page.getByLabel('I checked that this board belongs to this company').check();
  await page.getByRole('button', { name: 'Add source' }).click();
  await expect(page.getByRole('heading', { name: 'lever source' })).toBeVisible();
  await page.getByText('Edit company watch', { exact: true }).click();
  await page.getByLabel('Pause monitoring').check();
  await page.getByRole('button', { name: 'Save company', exact: true }).click();
  await expect(page.getByText('Monitoring paused', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Check now' })).toBeDisabled();
  await page.getByLabel('Pause monitoring').uncheck();
  await page.getByRole('button', { name: 'Save company', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Check now' })).toBeEnabled();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/company-${width}.png`, fullPage: true });
  }
  await page.getByText('Source settings and recent checks', { exact: true }).click();
  const sourceCard = page
    .locator('article')
    .filter({ has: page.getByRole('heading', { name: 'lever source' }) });
  await sourceCard.getByLabel('Check interval (hours)').fill('6');
  await sourceCard.getByRole('button', { name: 'Save source', exact: true }).click();
  await expect(sourceCard.getByText('Source settings saved.')).toBeVisible();
  execFileSync('../backend/.venv/bin/python', ['../scripts/seed-browser-jobs.py', companyId]);
  await page.getByRole('link', { name: 'All collected jobs', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Legal adviser', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Strategy manager', exact: true })).toBeVisible();
  await page.getByLabel('Search collected jobs').fill('Legal');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Strategy manager', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'Legal adviser', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Legal adviser', exact: true })).toBeVisible();
  await expect(page.getByText(/This role has no current assessment/)).toBeVisible();
  await page.getByRole('radio', { name: 'Not relevant', exact: true }).check();
  await page.getByLabel('Reason (optional)').fill('Synthetic feedback note');
  await page.getByRole('button', { name: 'Save feedback', exact: true }).click();
  await expect(page.getByText('Feedback saved.', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Reason (optional)')).toHaveValue('Synthetic feedback note');
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/job-${width}.png`, fullPage: true });
  }
  await page.getByRole('link', { name: 'Back to jobs', exact: true }).click();
  await expect(page.getByLabel('Search collected jobs')).toHaveValue('Legal');
  expect(new URL(page.url()).searchParams.get('company_id')).toBe(companyId);
});

test('discovery candidate → explicit company confirmation → persisted website', async ({
  page,
}) => {
  await page.goto('/companies');
  await page.getByLabel('Username').fill('owner');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByLabel('Company name', { exact: true }).fill('Synthetic Discovery');
  await page.getByRole('button', { name: 'Follow company' }).click();
  await expect(
    page.getByRole('heading', { name: 'Synthetic Discovery', exact: true }),
  ).toBeVisible();
  const companyId = new URL(page.url()).pathname.split('/').at(-1)!;
  execFileSync('../backend/.venv/bin/python', ['../scripts/seed-browser-discovery.py', companyId]);
  await page.reload();
  await page.getByRole('radio', { name: 'Use this page for Synthetic Discovery' }).check();
  await expect(page.getByRole('button', { name: 'Confirm company page' })).toBeDisabled();
  await page.getByLabel('I checked that the selected page belongs to Synthetic Discovery').check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/discovery-${width}.png`, fullPage: true });
  }
  await page.getByRole('button', { name: 'Confirm company page' }).click();
  await expect(
    page.getByText('Company page confirmed. A new source check is queued.'),
  ).toBeVisible();
  await page.getByText('Edit company watch', { exact: true }).click();
  await expect(page.getByLabel('Website or careers URL', { exact: true })).toHaveValue(
    'https://example.com/careers',
  );
  await page.reload();
  await page.getByText('Edit company watch', { exact: true }).click();
  await expect(page.getByLabel('Website or careers URL', { exact: true })).toHaveValue(
    'https://example.com/careers',
  );
  await expect(
    page.getByRole('radio', { name: 'Use this page for Synthetic Discovery' }),
  ).toHaveCount(0);
});

test('mock assessment worker → broad shortlist → changed preferences', async ({ page }) => {
  await page.goto('/companies');
  await page.getByLabel('Username').fill('owner');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Companies', exact: true })).toBeVisible();
  const session = await (await page.request.get('/api/v1/auth/me')).json();
  const headers = { Origin: 'http://127.0.0.1:5173', 'X-CSRF-Token': session.csrf_token };
  const profile = await (await page.request.get('/api/v1/profile')).json();
  const saved = await page.request.patch('/api/v1/profile', {
    headers: { ...headers, 'If-Match': `"${profile.revision}"` },
    data: {
      facts: { summary: 'Synthetic candidate with planning and advisory experience.' },
      preferences: { desired_roles: ['Strategy'] },
    },
  });
  expect(saved.ok()).toBe(true);
  const settings = await (await page.request.get('/api/v1/settings/ai')).json();
  const matching = settings.tasks.find((task: { task: string }) => task.task === 'job_matching');
  expect(
    (
      await page.request.patch('/api/v1/settings/ai', {
        headers: { ...headers, 'If-Match': `"${matching.revision}"` },
        data: { task: 'job_matching', config: { model: 'mock/job-matching-v1' } },
      })
    ).ok(),
  ).toBe(true);
  await page.getByLabel('Company name', { exact: true }).fill('Synthetic Entertainment');
  await page.getByRole('button', { name: 'Follow company' }).click();
  await expect(page).toHaveURL(/\/companies\/[0-9a-f-]{36}$/);
  await expect(
    page.getByRole('heading', { name: 'Synthetic Entertainment', exact: true }),
  ).toBeVisible();
  const companyId = new URL(page.url()).pathname.split('/').at(-1)!;
  await page.getByLabel('Job board provider').selectOption('lever');
  await page.getByLabel('Board identifier').fill('synthetic-matching');
  await page.getByLabel('I checked that this board belongs to this company').check();
  await page.getByRole('button', { name: 'Add source' }).click();
  await expect(page.getByRole('heading', { name: 'lever source' })).toBeVisible();
  execFileSync('../backend/.venv/bin/python', [
    '../scripts/seed-browser-jobs.py',
    companyId,
    '--matching',
  ]);
  const inventoryPath = `/api/v1/jobs?view=all&company_id=${companyId}`;
  await expect
    .poll(
      async () => {
        const inventory = await (await page.request.get(inventoryPath)).json();
        return inventory.items.filter(
          (job: { assessment_status: string }) => job.assessment_status === 'assessed',
        ).length;
      },
      { timeout: 60_000 },
    )
    .toBe(3);
  await page.goto(`/jobs?company_id=${companyId}`);
  await expect(page.getByRole('link', { name: 'Strategy manager', exact: true })).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Business transformation lead', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Legal adviser', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'Business transformation lead', exact: true }).click();
  await expect(page.getByText('Possible', { exact: true })).toBeVisible();
  await expect(page.getByText(/Mock result for development/)).toBeVisible();
  await page.getByText('Supporting evidence', { exact: true }).first().click();
  await expect(
    page
      .getByText('Plan organisational transformation in a new industry.', { exact: true })
      .first(),
  ).toBeVisible();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `test-results/assessment-${width}.png`, fullPage: true });
  }
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Edit profile' }).click();
  await page.getByLabel('Desired roles or functions — one per line').fill('Legal advice');
  await page.getByLabel('I have reviewed my experience and preferences.').check();
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByText('Legal advice', { exact: true })).toBeVisible();
  await expect
    .poll(
      async () => {
        const shortlist = await (
          await page.request.get(`/api/v1/jobs?company_id=${companyId}`)
        ).json();
        return shortlist.items.map((job: { posting: { title: string } }) => job.posting.title);
      },
      { timeout: 60_000 },
    )
    .toEqual(['Legal adviser']);
  await page.goto(`/jobs?company_id=${companyId}`);
  await expect(page.getByRole('link', { name: 'Legal adviser', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'All jobs', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Strategy manager', exact: true })).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Business transformation lead', exact: true }),
  ).toBeVisible();
});
