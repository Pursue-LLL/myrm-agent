import { test, expect } from '@playwright/test';

import { completeOnboardingForE2e, ensureLoggedIn } from './helpers/auth';
import {
  installMigrationDismissInitScript,
  prepareChatPageForE2e,
} from './helpers/prepareChatPageForE2e';
import {
  E2E_CONFIG_DEVICE_ID,
  seedE2eProvidersFromEnv,
  hasE2eLlmEnv,
} from './helpers/seedE2eProviders';

test.describe('Agent gallery builtin tools smoke', () => {
  test.describe.configure({ timeout: 120_000 });

  test.skip(
    !process.env.PLAYWRIGHT_RUN_GALLERY_SMOKE || !hasE2eLlmEnv(),
    'Set PLAYWRIGHT_RUN_GALLERY_SMOKE=1 and load BASIC_* from .env.test with :8080 + :3000',
  );

  test('preset gallery loads 24 builtins and shows developer tool chips', async ({ page, request }) => {
    await installMigrationDismissInitScript(page);
    await completeOnboardingForE2e(request);
    await ensureLoggedIn(page, request);
    await seedE2eProvidersFromEnv(request, { deviceId: E2E_CONFIG_DEVICE_ID });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await prepareChatPageForE2e(page);

    const agentRadio = page.getByRole('radio', { name: /智能代理|Smart Agent/i });
    await expect(agentRadio).toBeVisible({ timeout: 30_000 });
    if (!(await agentRadio.isChecked())) {
      await agentRadio.click();
    }

    const developerCard = page.getByRole('button').filter({ hasText: /Code Developer|代码开发/i }).first();
    await expect(developerCard).toBeVisible({ timeout: 30_000 });
    await expect(developerCard).toContainText(/file_ops|File Ops|文件操作/i);
    await expect(developerCard).toContainText(/code_execute|Code Execute|代码执行/i);

    const audioCard = page.getByRole('button').filter({ hasText: /Audio Assistant|音频助手/i }).first();
    await expect(audioCard).toBeVisible({ timeout: 15_000 });
    await expect(audioCard).toContainText(/tts|Text to Speech|语音生成/i);

    const hrCard = page.getByRole('button').filter({ hasText: /HR Resume Screener|简历/i }).first();
    await expect(hrCard).toBeVisible({ timeout: 15_000 });
    await expect(hrCard).toContainText(/file_ops|File Ops|文件操作/i);
    await expect(hrCard).not.toContainText(/code_execute|Code Execute|代码执行/i);
  });
});
