import { test, expect } from '@playwright/test';

import { ensureLoggedIn, completeOnboardingForE2e } from './helpers/auth';
import {
  installMigrationDismissInitScript,
  prepareChatPageForE2e,
} from './helpers/prepareChatPageForE2e';
import { hasE2eLlmEnv } from './helpers/seedE2eProviders';

test.describe('Planning UI smoke', () => {
  test.describe.configure({ timeout: 120_000 });

  test.skip(
    !process.env.PLAYWRIGHT_RUN_PLANNING_UI_SMOKE || !hasE2eLlmEnv(),
    'Set PLAYWRIGHT_RUN_PLANNING_UI_SMOKE=1 and LLM keys from .env.test with :8080 + :3000',
  );

  test('builtin tools panel shows Planning toggle with todo_write copy', async ({ page, request }) => {
    await completeOnboardingForE2e(request);
    await ensureLoggedIn(page, request);
    await installMigrationDismissInitScript(page);
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await prepareChatPageForE2e(page);

    const builtinCard = page.getByText(/Built-in Tools|内置工具/i).first();
    await expect(builtinCard).toBeVisible({ timeout: 15_000 });
    await builtinCard.click();

    const planningCard = page.getByTestId('builtin-planning');
    await expect(planningCard).toBeVisible({ timeout: 10_000 });
    await expect(planningCard).toContainText(/Multi-Step Progress|多步|Planning|任务规划/i);

    const planningDesc = page.locator('[data-testid="builtin-planning"]').locator('..');
    await expect(planningDesc).toContainText(/todo_write|进度|progress/i);
  });
});
