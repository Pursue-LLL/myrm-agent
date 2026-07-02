import { test, expect } from '@playwright/test';

import { ensureLoggedIn } from './helpers/auth';
import { seedE2eProvidersFromEnv, hasE2eLlmEnv } from './helpers/seedE2eProviders';
import {
  DELEGATE_SLEEP_QUERY,
  seedSubagentChat,
} from './helpers/subagentDashboardE2e';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

test.describe('Subagent Dashboard', () => {
  test.describe.configure({ mode: 'serial', timeout: 180_000 });

  test.skip(
    !process.env.PLAYWRIGHT_RUN_SUBAGENT_DASHBOARD_E2E || !hasE2eLlmEnv(),
    'Set PLAYWRIGHT_RUN_SUBAGENT_DASHBOARD_E2E=1 and load BASIC_API_KEY/BASIC_MODEL from .env.test with backend :8080 + frontend :3000',
  );

  test('delegate via chat -> dashboard -> cancel subagent', async ({ page, request }) => {
    await ensureLoggedIn(page, request);
    const deviceId = await page.evaluate(() => {
      const existing = localStorage.getItem('config-device-id');
      if (existing) return existing;
      const id = crypto.randomUUID();
      localStorage.setItem('config-device-id', id);
      return id;
    });
    await seedE2eProvidersFromEnv(request, { force: true, deviceId });

    const chatId = await seedSubagentChat(request);
    await page.goto(`/${chatId}`, { waitUntil: 'domcontentloaded' });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.locator('textarea[data-chat-input]')).toBeVisible({ timeout: 30_000 });

    const modelButton = page.getByRole('button', { name: /未配置|Not configured|MiniMax|M2\.7/i }).first();
    await expect(modelButton).toBeVisible({ timeout: 30_000 });
    const modelLabel = await modelButton.innerText();
    test.skip(
      /未配置|Not configured/i.test(modelLabel),
      'WebUI provider not ready for this browser deviceId — configure model in Settings once, then re-run',
    );

    const input = page.locator('textarea[data-chat-input]');
    await input.fill(DELEGATE_SLEEP_QUERY);
    await input.press('Enter');

    await expect(page.getByTestId('subagent-dashboard-trigger')).toBeVisible({ timeout: 120_000 });
    await expect(page.getByTestId('subagent-dashboard-trigger')).toContainText(/1|active|running|活跃/i, {
      timeout: 120_000,
    });

    await page.getByTestId('subagent-dashboard-trigger').click();
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
