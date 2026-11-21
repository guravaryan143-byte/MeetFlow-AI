import { expect, test } from '@playwright/test';

test('demo journey: transcript intelligence, task workflows, approvals, and navigation', async ({ page }) => {
  const email = `e2e-${Date.now()}@meetflow.local`;
  const password = 'StrongPass123!';

  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Meetings end.')).toBeVisible();
  await page.getByRole('link', { name: 'Start Meeting' }).click();
  await page.getByLabel('Full Name').fill('E2E Demo Owner');
  await page.getByLabel('Organization Name').fill(`E2E Workspace ${Date.now()}`);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Create Workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();

  await page.getByRole('link', { name: 'Meetings' }).click();
  await page.getByPlaceholder('Meeting title (e.g., Q4 Product Launch Sync)').fill('Launch Decision Meeting');
  await page.getByLabel('Meeting date').fill('2026-11-20');
  await page.getByPlaceholder('Maya Chen, Jordan Lee').fill('Maya Chen, Jordan Lee');
  await page.getByPlaceholder('[00:00:10] Maya Lin: The product launch date is confirmed as December 10.')
    .fill(
      '[00:00:10] Maya Chen: The product launch date is confirmed as December 10.\n' +
      '[00:00:20] Maya Chen: I will prepare the security checklist by December 5.',
    );
  await page.getByRole('button', { name: 'Process meeting' }).click();
  const firstMeetingLink = page.getByRole('link', { name: 'Launch Decision Meeting' });
  await expect(firstMeetingLink).toBeVisible();
  await expect(page.getByText('Meeting processed and saved.')).toBeVisible();
  await firstMeetingLink.click();
  await expect(page.getByRole('heading', { name: 'Launch Decision Meeting' })).toBeVisible();
  await page.getByRole('button', { name: 'Correct Speaker' }).first().click();
  await page.getByLabel('Corrected speaker name').fill('Maya Chen (verified)');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Speaker correction saved.')).toBeVisible();
  await page.getByRole('link', { name: 'All meetings' }).click();

  const token = await page.evaluate(() => localStorage.getItem('meetflow_token'));
  expect(token).toBeTruthy();
  const approvalsResponse = await page.request.get('http://127.0.0.1:8001/api/approvals', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(approvalsResponse.ok()).toBeTruthy();
  const approvals = (await approvalsResponse.json()).approvals;
  expect(approvals.length).toBeGreaterThan(0);
  const unauthorizedExecution = await page.request.post(
    `http://127.0.0.1:8001/api/approvals/${approvals[0].id}/execute`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(unauthorizedExecution.status()).toBe(403);

  await page.getByLabel('Uploaded meeting title').fill('Launch Change Meeting');
  await page.getByLabel('Transcript file').setInputFiles({
    name: 'launch-change.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(
      '[00:00:10] Maya Chen: I propose moving the product launch date to December 15.\n' +
      '[00:00:25] Maya Chen: I will send the revised launch plan by December 7.',
    ),
  });
  await page.getByRole('button', { name: 'Upload & Process' }).click();
  await expect(page.getByRole('link', { name: 'Launch Change Meeting' })).toBeVisible();
  await expect(page.getByText('Transcript uploaded and processed.')).toBeVisible();

  await page.getByRole('link', { name: 'Decisions', exact: true }).click();
  await expect(page.getByText('The product launch date is confirmed as December 10.', { exact: true })).toBeVisible();
  await expect(page.getByText('I propose moving the product launch date to December 15.', { exact: true })).toBeVisible();
  await page.getByPlaceholder('Search decision, statement, or meeting').fill('December 10');
  await expect(page.getByText('The product launch date is confirmed as December 10.', { exact: true })).toBeVisible();
  await expect(page.getByText('I propose moving the product launch date to December 15.', { exact: true })).toHaveCount(0);
  await page.getByPlaceholder('Search decision, statement, or meeting').fill('');
  await page.getByLabel('Filter decisions by type').selectOption('PROPOSED');
  await expect(page.getByText('I propose moving the product launch date to December 15.', { exact: true })).toBeVisible();
  await page.getByLabel('Filter decisions by type').selectOption('ALL');

  await page.getByRole('link', { name: 'Conflict Review' }).click();
  await expect(page.getByText('DEADLINE_CHANGE')).toBeVisible();
  await expect(page.getByText('The product launch date is confirmed as December 10.', { exact: true })).toBeVisible();
  await expect(page.getByText('I propose moving the product launch date to December 15.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm New Decision (Supersede Old)' }).click();
  await expect(page.getByText('RESOLVED_ADOPT_NEW')).toBeVisible();

  await page.getByRole('link', { name: 'Action Items' }).click();
  await expect(page.getByRole('heading', { name: /I will prepare the security checklist by December 5/ })).toBeVisible();
  await page.getByPlaceholder('What needs to be done?').fill('Review release checklist');
  await page.getByRole('button', { name: 'Save action item' }).click();
  const manualTask = page.locator('article').filter({
    has: page.getByRole('heading', { name: 'Review release checklist', exact: true }),
  });
  await expect(manualTask).toBeVisible();
  await manualTask.getByLabel(/External task provider/).selectOption('trello');
  await manualTask.getByRole('button', { name: 'Prepare sync · approval required' }).click();
  await expect(page.getByText('External sync is ready for human review in the Approval Inbox.')).toBeVisible();
  await page.getByRole('button', { name: 'Prepare reminder' }).first().click();
  await expect(page.getByText('Reminder prepared and sent to the Approval Inbox for review.')).toBeVisible();

  await page.getByRole('link', { name: 'Reminders' }).click();
  await expect(page.getByRole('heading', { name: 'Reminders' })).toBeVisible();
  await page.getByLabel('Action item').selectOption({ label: 'Review release checklist' });
  await page.getByLabel('Reminder type').selectOption('OVERDUE');
  await page.getByRole('button', { name: 'Send to approval' }).click();
  await expect(page.getByText('Reminder prepared. Review it in the Approval Inbox before it can be sent.')).toBeVisible();
  await expect(page.getByText('Reminder history · 2')).toBeVisible();

  await page.getByRole('link', { name: 'Action Items' }).click();
  await manualTask.getByRole('button', { name: 'Mark completed' }).click();
  await expect(manualTask.getByText('COMPLETED', { exact: true })).toBeVisible();

  await page.getByRole('link', { name: 'Weekly Digests' }).click();
  await page.getByLabel('Delivery day').selectOption('Tuesday');
  await page.getByLabel('Delivery time').fill('10:30');
  await page.getByRole('button', { name: 'Generate digest' }).click();
  await expect(page.getByText('Digest generated and queued for approval.')).toBeVisible();

  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Approval Inbox' }).click();
  await page.getByLabel('Filter approvals by status').selectOption('PENDING');
  await page.getByRole('button', { name: 'Reject' }).first().click();
  await expect(page.getByRole('status').filter({ hasText: 'Action rejected.' })).toBeVisible();
  await page.getByLabel('Filter approvals by status').selectOption('ALL');
  await page.getByLabel(/Review note/).first().fill('Verified the source evidence before approval.');
  await page.getByRole('button', { name: 'Approve' }).first().click();
  await page.getByRole('button', { name: 'Execute via Authorized Adapter' }).first().click();
  await expect(page.getByRole('status').filter({ hasText: 'Approved action executed.' })).toBeVisible();

  await page.getByRole('button', { name: 'Sign Out' }).click();
  await expect(page.getByRole('heading', { name: 'Sign in to MeetFlow AI' })).toBeVisible();
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  await page.getByRole('link', { name: 'Meetings' }).click();
  await expect(page.getByRole('link', { name: 'Launch Decision Meeting' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Launch Change Meeting' })).toBeVisible();

  const dashboardRoutes = [
    { link: 'Overview', heading: 'Overview' },
    { link: 'Meetings', heading: 'Meetings' },
    { link: 'Decisions', heading: 'Decisions' },
    { link: 'Conflict Review', heading: 'Conflict review' },
    { link: 'Action Items', heading: 'Action items' },
    { link: 'Reminders', heading: 'Reminders' },
    { link: 'Approval Inbox', heading: 'Approval inbox' },
    { link: 'Decision DNA', heading: 'Decision DNA' },
    { link: 'Commitment Radar', heading: 'Commitment radar' },
    { link: 'Weekly Digests', heading: 'Weekly digests' },
    { link: 'Analytics', heading: 'Execution analytics' },
    { link: 'Integrations', heading: 'Integrations' },
    { link: 'Settings', heading: 'Workspace settings' },
  ];
  for (const route of dashboardRoutes) {
    await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: route.link, exact: true }).click();
    await expect(page.getByRole('heading', { name: route.heading })).toBeVisible();
  }
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Integrations' }).click();
  await page.getByRole('button', { name: 'Connect workspace' }).first().click();
  await expect(page.getByRole('button', { name: 'Refresh connection' }).first()).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(page.locator('#primary-navigation').getByRole('link', { name: 'Reminders' })).toBeVisible();
  await page.locator('#primary-navigation').getByRole('link', { name: 'Reminders' }).click();
  await expect(page.getByRole('heading', { name: 'Reminders' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible();
});
