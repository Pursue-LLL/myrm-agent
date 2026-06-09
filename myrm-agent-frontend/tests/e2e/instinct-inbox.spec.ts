import { test, expect } from '@playwright/test';

import { ensureLoggedIn } from './helpers/auth';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

test.describe('Instinct Inbox', () => {
  test.describe.configure({ mode: 'serial' });

  test.skip(
    !process.env.PLAYWRIGHT_RUN_INSTINCT_INBOX_E2E,
    'Set PLAYWRIGHT_RUN_INSTINCT_INBOX_E2E=1 with backend :8080 and frontend :3000 running',
  );

  test('clone agent -> inbox lists drafts -> approve and dismiss', async ({ page, request }) => {
    await ensureLoggedIn(page, request);

    const cloneRes = await request.post(`${apiBase}/api/v1/user-agents/builtin-general/clone`, {
      data: { name: `E2E Inbox ${Date.now()}` },
    });
    expect(cloneRes.ok()).toBeTruthy();
    const cloneBody = (await cloneRes.json()) as { data: { id: string } };
    const clonedAgentId = cloneBody.data.id;

    const seedRes = await request.post(
      `${apiBase}/api/v1/skills/drafts/test/seed-mock?agent_id=${encodeURIComponent(clonedAgentId)}`,
    );
    expect(seedRes.ok()).toBeTruthy();

    const pendingBefore = await request.get(`${apiBase}/api/v1/skills/drafts?status=PENDING_REVIEW`);
    expect(pendingBefore.ok()).toBeTruthy();
    const pendingBody = (await pendingBefore.json()) as { total: number };
    expect(pendingBody.total).toBeGreaterThanOrEqual(2);

    await page.goto(`/settings/agents?agentId=${clonedAgentId}`, {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByText(/加载中|Loading/i)).toBeHidden({ timeout: 30_000 });
    await expect(page.getByRole('heading', { name: /编辑智能体|Edit Agent/i })).toBeVisible({
      timeout: 30_000,
    });

    const inboxTab = page.getByTestId('agent-tab-inbox');
    await expect(inboxTab).toBeVisible({ timeout: 10_000 });
    await inboxTab.click();

    const panel = page.getByTestId('instinct-inbox-panel');
    await expect(panel).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('instinct-draft-card')).toHaveCount(2, { timeout: 15_000 });

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
    await page.getByTestId('agent-tab-inbox').click();

    await expect(page.getByTestId('instinct-inbox-panel')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('instinct-approve-btn')).toHaveCount(0);
    await expect(page.getByTestId('instinct-dismiss-btn')).toHaveCount(0);
  });
});
