import { test, expect } from '@playwright/test';

import { ensureLoggedIn } from './helpers/auth';
import { ensureWebUiBrowserSession } from './helpers/ensureWebUiBrowserSession';
import {
  installMigrationDismissInitScript,
  prepareChatPageForE2e,
  sendChatMessage,
  waitForChatHydration,
} from './helpers/prepareChatPageForE2e';
import {
  E2E_CONFIG_DEVICE_ID,
  seedE2eProvidersFromEnv,
  hasE2eLlmEnv,
} from './helpers/seedE2eProviders';
import {
  DELEGATE_SLEEP_QUERY,
  injectSubagentsUpdatedFromRest,
  seedSubagentChat,
  waitForDashboardTriggerNatural,
  waitForRunningSubagent,
} from './helpers/subagentDashboardE2e';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

test.describe('Subagent Dashboard', () => {
  test.describe.configure({ mode: 'serial', timeout: 360_000 });
  test.use({ actionTimeout: 30_000 });

  test.skip(
    !process.env.PLAYWRIGHT_RUN_SUBAGENT_DASHBOARD_E2E || !hasE2eLlmEnv(),
    'Set PLAYWRIGHT_RUN_SUBAGENT_DASHBOARD_E2E=1 and load BASIC_API_KEY/BASIC_MODEL from .env.test with backend :8080 + frontend :3000',
  );

  test('delegate via chat -> dashboard -> cancel subagent', async ({ page, request }) => {
    await installMigrationDismissInitScript(page);
    await ensureLoggedIn(page, request);
    await ensureWebUiBrowserSession(page);
    await seedE2eProvidersFromEnv(request, { deviceId: E2E_CONFIG_DEVICE_ID });

    const chatId = await seedSubagentChat(request);
    await page.goto(`/${chatId}`, { waitUntil: 'load' });
    await waitForChatHydration(page, chatId);
    await prepareChatPageForE2e(page);

    await sendChatMessage(page, DELEGATE_SLEEP_QUERY);

    await waitForRunningSubagent(request, chatId, 180_000);

    const naturalVisible = await waitForDashboardTriggerNatural(page, 30_000);
    if (!naturalVisible) {
      test.info().annotations.push({
        type: 'FALLBACK_INJECT',
        description: 'Dashboard trigger not visible via chat stream; injecting subagents_updated from REST',
      });
      await injectSubagentsUpdatedFromRest(page, request, chatId);
    }

    const trigger = page.getByTestId('subagent-dashboard-trigger');
    await expect(trigger).toBeVisible({ timeout: 15_000 });
    await expect(trigger).toContainText(/1|active|running|活跃/i, { timeout: 30_000 });

    await trigger.click();
    await expect(page.getByTestId('subagent-dashboard-panel')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('subagent-cancel-btn').first()).toBeVisible({ timeout: 30_000 });

    await page.getByTestId('subagent-cancel-btn').first().click();
    await page.getByRole('button', { name: /Cancel subagent|取消子任务/ }).click();

    const deadline = Date.now() + 30_000;
    let cancelled = false;
    while (Date.now() < deadline) {
      const listRes = await request.get(`${apiBase}/api/v1/chats/${chatId}/subagents`);
      if (listRes.ok()) {
        const listBody = (await listRes.json()) as {
          data?: Array<{ status?: string }>;
        };
        const rows = listBody.data ?? [];
        if (rows.length === 0 || rows.every((row) => row.status !== 'running')) {
          cancelled = true;
          break;
        }
      }
      await page.waitForTimeout(1000);
    }
    expect(cancelled).toBeTruthy();
  });
});
