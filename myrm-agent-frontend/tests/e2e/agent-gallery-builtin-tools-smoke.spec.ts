import { test, expect } from '@playwright/test';

import { ensureLoggedIn, completeOnboardingForE2e } from './helpers/auth';
import {
  installMigrationDismissInitScript,
  prepareChatPageForE2e,
} from './helpers/prepareChatPageForE2e';
import {
  E2E_CONFIG_DEVICE_ID,
  seedE2eProvidersFromEnv,
  hasE2eLlmEnv,
} from './helpers/seedE2eProviders';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

test.describe('Agent gallery builtin tools smoke', () => {
  test.describe.configure({ timeout: 120_000 });

  test.skip(
    !process.env.PLAYWRIGHT_RUN_GALLERY_SMOKE || !hasE2eLlmEnv(),
    'Set PLAYWRIGHT_RUN_GALLERY_SMOKE=1 and load BASIC_* from .env.test with :8080 + :3000',
  );

  test('preset gallery loads 24 builtins and shows developer tool chips', async ({ page, request }) => {
    await completeOnboardingForE2e(request);
    await ensureLoggedIn(page, request);
    await seedE2eProvidersFromEnv(request, { deviceId: E2E_CONFIG_DEVICE_ID });
    await installMigrationDismissInitScript(page);

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await prepareChatPageForE2e(page);

    const agentRadio = page.getByRole('radio', { name: /智能代理|Smart Agent/i });
    await expect(agentRadio).toBeVisible({ timeout: 30_000 });
    if (!(await agentRadio.isChecked())) {
      await agentRadio.click();
    }

    const listRes = await request.get(`${apiBase}/api/v1/user-agents?page=1&page_size=50`, {
      headers: { 'X-Device-Id': E2E_CONFIG_DEVICE_ID },
      timeout: 60_000,
    });
    expect(listRes.ok()).toBeTruthy();
    const agentsPayload = (await listRes.json()) as {
      data?: { items?: Array<{ is_built_in?: boolean; name?: string }> };
    };
    const builtinCount = (agentsPayload.data?.items ?? []).filter((item) => item.is_built_in).length;
    expect(builtinCount).toBe(24);

    const developerCard = page.getByRole('button').filter({ hasText: /Code Developer|代码开发/i }).first();
    await expect(developerCard).toBeVisible({ timeout: 30_000 });
    await expect(developerCard).toContainText(/文件操作|File Ops|file_ops/i);
    await expect(developerCard).toContainText(/代码执行|Code Execute|code_execute/i);

    const audioCard = page.getByRole('button').filter({ hasText: /Audio Assistant|音频助手/i }).first();
    await expect(audioCard).toBeVisible({ timeout: 15_000 });
    await expect(audioCard).toContainText(/tts|Text to Speech|语音生成/i);
  });
});
