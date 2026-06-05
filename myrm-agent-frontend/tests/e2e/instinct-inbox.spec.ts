import { test, expect } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

async function dismissBatchApprovalDialog(
  page: import('@playwright/test').Page,
): Promise<void> {
  const batchDialog = page.getByRole('dialog', { name: /批量审批|Batch/i });
  if (!(await batchDialog.isVisible({ timeout: 3_000 }).catch(() => false))) {
    return;
  }
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.keyboard.press('Escape');
    if (!(await batchDialog.isVisible().catch(() => false))) {
      return;
    }
    const vaulOverlay = page.locator('[data-vaul-overlay]').last();
    if (await vaulOverlay.isVisible().catch(() => false)) {
      await vaulOverlay.click({ position: { x: 12, y: 12 }, force: true });
    }
    const radixOverlay = page.locator('[data-slot="dialog-overlay"]').last();
    if (await radixOverlay.isVisible().catch(() => false)) {
      await radixOverlay.click({ position: { x: 12, y: 12 }, force: true });
    }
  }
  await expect(batchDialog).toBeHidden({ timeout: 5_000 });
}

async function ensureLoggedIn(
  page: import('@playwright/test').Page,
  request: import('@playwright/test').APIRequestContext,
): Promise<void> {
  const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD ?? 'Playwright1234!';

  const statusRes = await request.get(`${apiBase}/webui/auth/status`);
  expect(statusRes.ok()).toBeTruthy();
  const status = (await statusRes.json()) as { is_setup_done: boolean };

  if (!status.is_setup_done) {
    const tokenRes = await request.post(`${apiBase}/webui/auth/generate-setup-token`);
    expect(tokenRes.ok()).toBeTruthy();
    const { temp_token: tempToken } = (await tokenRes.json()) as { temp_token: string };

    await page.goto(`/auth/setup?token=${tempToken}`, { waitUntil: 'domcontentloaded' });
    await page.getByPlaceholder(/Enter your password|输入您的密码/).first().fill(adminPassword);
    await page.getByPlaceholder(/Re-enter your password|重新输入您的密码/).fill(adminPassword);
    await page.getByRole('button', { name: /Set [Pp]assword|设置密码/ }).click();
    await page.waitForURL((url) => !url.pathname.includes('/auth/setup'), { timeout: 15_000 });
    return;
  }

  await request.post(`${apiBase}/webui/auth/logout`);
  const tokenRes = await request.post(`${apiBase}/webui/auth/generate-setup-token`);
  expect(tokenRes.ok()).toBeTruthy();
  const { temp_token: tempToken } = (await tokenRes.json()) as { temp_token: string };

  await page.goto(`/auth/login?token=${encodeURIComponent(tempToken)}`, {
    waitUntil: 'domcontentloaded',
  });
  await page.waitForURL((url) => url.pathname === '/' || url.pathname === '', { timeout: 30_000 });
}

test.describe('Instinct Inbox', () => {
  test.skip(
    !process.env.PLAYWRIGHT_RUN_INSTINCT_INBOX_E2E,
    'Set PLAYWRIGHT_RUN_INSTINCT_INBOX_E2E=1 with backend :8080 and frontend :3000 running',
  );

  test('clone agent -> inbox lists drafts -> approve and dismiss', async ({ page, request }) => {
    const seedRes = await request.post(`${apiBase}/api/v1/skills/drafts/test/seed-mock`);
    expect(seedRes.ok()).toBeTruthy();

    const pendingBefore = await request.get(`${apiBase}/api/v1/skills/drafts?status=PENDING_REVIEW`);
    expect(pendingBefore.ok()).toBeTruthy();
    const pendingBody = (await pendingBefore.json()) as { total: number };
    expect(pendingBody.total).toBeGreaterThanOrEqual(2);

    await ensureLoggedIn(page, request);

    const cloneRes = await request.post(`${apiBase}/api/v1/user-agents/builtin-general/clone`, {
      data: { name: `E2E Inbox ${Date.now()}` },
    });
    expect(cloneRes.ok()).toBeTruthy();
    const cloneBody = (await cloneRes.json()) as { data: { id: string } };
    const clonedAgentId = cloneBody.data.id;

    await page.goto(`/settings/agents?agentId=${clonedAgentId}`, {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByText(/加载中|Loading/i)).toBeHidden({ timeout: 15_000 });
    await expect(page.getByRole('heading', { name: /编辑智能体|Edit Agent/i })).toBeVisible({
      timeout: 10_000,
    });

    await page.getByRole('dialog', { name: /批量审批|Batch/i }).waitFor({ state: 'visible', timeout: 8_000 }).catch(() => undefined);
    await dismissBatchApprovalDialog(page);

    const inboxTab = page.getByTestId('agent-tab-inbox');
    await expect(inboxTab).toBeVisible({ timeout: 10_000 });
    await inboxTab.click();
    await dismissBatchApprovalDialog(page);

    const panel = page.getByTestId('instinct-inbox-panel');
    await expect(panel).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('instinct-draft-card')).toHaveCount(2, { timeout: 10_000 });

    const approveCard = page.locator('[data-draft-name="test-frontend-approve"]');
    await approveCard.getByTestId('instinct-approve-btn').click();
    await expect(approveCard).toHaveCount(0, { timeout: 15_000 });

    const dismissCard = page.locator('[data-draft-name="test-frontend-reject"]');
    await dismissCard.getByTestId('instinct-dismiss-btn').click();
    await expect(dismissCard).toHaveCount(0, { timeout: 15_000 });

    await expect(page.getByTestId('instinct-inbox-empty')).toBeVisible({ timeout: 10_000 });

    const pendingRes = await request.get(`${apiBase}/api/v1/skills/drafts?status=PENDING_REVIEW`);
    expect(pendingRes.ok()).toBeTruthy();
    const pending = (await pendingRes.json()) as { total: number };
    expect(pending.total).toBe(0);
  });

  test('builtin-general inbox is readonly (no approve/dismiss buttons)', async ({ page, request }) => {
    await request.post(`${apiBase}/api/v1/skills/drafts/test/seed-mock`);
    await ensureLoggedIn(page, request);

    await page.goto('/settings/agents?agentId=builtin-general', {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByText(/加载中|Loading/i)).toBeHidden({ timeout: 15_000 });
    await page.getByRole('dialog', { name: /批量审批|Batch/i }).waitFor({ state: 'visible', timeout: 8_000 }).catch(() => undefined);
    await dismissBatchApprovalDialog(page);

    await page.getByTestId('agent-tab-inbox').click();
    await dismissBatchApprovalDialog(page);

    await expect(page.getByTestId('instinct-draft-card').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('instinct-approve-btn')).toHaveCount(0);
    await expect(page.getByTestId('instinct-dismiss-btn')).toHaveCount(0);
    await expect(page.getByText(/内置智能体（只读）|Built-in \(Read-only\)/)).toBeVisible({ timeout: 5_000 });
  });
});
