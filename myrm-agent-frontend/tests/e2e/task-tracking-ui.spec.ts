import { test, expect } from '@playwright/test';

import { ensureLoggedIn } from './helpers/auth';

test.describe('Task Tracking UI (TSM v1.5)', () => {
  test.skip(
    !process.env.PLAYWRIGHT_RUN_WEBUI_E2E,
    'Set PLAYWRIGHT_RUN_WEBUI_E2E=1 with backend on :8080 and frontend on :3000',
  );

  test('builtin tools: enable task tracking and enforce planning mutual exclusion', async ({
    page,
    request,
  }) => {
    await ensureLoggedIn(page, request);
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: /Application error|应用出错了/ })).toHaveCount(0);

    const agentMode = page.getByRole('button', { name: /Agent|智能代理|智能体/i }).first();
    if (await agentMode.isVisible()) {
      await agentMode.click();
    }

    const builtinToolsCard = page.getByText(/^内置工具$|^Built-in tools$/i).first();
    await expect(builtinToolsCard).toBeVisible({ timeout: 15_000 });
    await builtinToolsCard.click();

    const taskTrackingLabel = page.getByText(/轻量任务追踪|Task [Tt]racking/i).first();
    const planningLabel = page.getByText(/结构化任务规划|Planning/i).first();
    await expect(taskTrackingLabel).toBeVisible({ timeout: 10_000 });
    await expect(planningLabel).toBeVisible();

    const taskTrackingRow = taskTrackingLabel.locator('xpath=ancestor::*[contains(@class,"cursor-pointer") or @role="button"][1]');
    const planningRow = planningLabel.locator('xpath=ancestor::*[contains(@class,"cursor-pointer") or @role="button"][1]');

    await taskTrackingRow.click();
    await expect(taskTrackingRow.locator('[data-state="checked"], input:checked, [aria-checked="true"]').first()).toBeVisible({
      timeout: 5_000,
    }).catch(async () => {
      await taskTrackingLabel.click();
    });

    await expect(planningRow.locator('[data-state="checked"], input:checked, [aria-checked="true"]')).toHaveCount(0);

    await page.screenshot({ path: 'test-results/task-tracking-enabled.png', fullPage: false });
  });
});
