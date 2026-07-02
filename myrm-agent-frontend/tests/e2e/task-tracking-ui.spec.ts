import { test, expect } from '@playwright/test';

import { ensureLoggedIn } from './helpers/auth';
import { hasE2eLlmEnv, seedE2eProvidersFromEnv } from './helpers/seedE2eProviders';
import { enableTaskTrackingInDialog, openBuiltinToolsDialog } from './helpers/taskTrackingUi';

test.describe('Task Tracking UI (TSM v1.5)', () => {
  test.skip(
    !process.env.PLAYWRIGHT_RUN_WEBUI_E2E,
    'Set PLAYWRIGHT_RUN_WEBUI_E2E=1 with backend on :8080 and frontend on :3000',
  );

  test.use({ locale: 'zh-CN', viewport: { width: 1400, height: 900 } });

  test('enable task tracking and enforce planning mutual exclusion', async ({ page, request }) => {
    await ensureLoggedIn(page, request);
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: /Application error|应用出错了/ })).toHaveCount(0);

    await openBuiltinToolsDialog(page);
    await expect(page.getByTestId('builtin-task_tracking')).toBeVisible({ timeout: 10_000 });

    await page.evaluate(() => {
      document.querySelectorAll('[data-radix-scroll-area-viewport]').forEach((viewport) => {
        viewport.scrollTop = viewport.scrollHeight;
      });
    });

    const taskCard = page.getByTestId('builtin-task_tracking');
    await taskCard.evaluate((el) => {
      el.scrollIntoView({ block: 'center', inline: 'nearest' });
      (el as HTMLElement).click();
    });

    await expect(taskCard).toHaveClass(/border-primary/);
    await expect(page.getByTestId('builtin-planning')).not.toHaveClass(/border-primary/);
  });

  test('WebUI chat flow renders Execution checklist ProgressSteps', async ({ page, request }) => {
    test.skip(!hasE2eLlmEnv(), 'Requires BASIC_API_KEY and BASIC_MODEL in env (.env.test)');
    test.setTimeout(240_000);

    await ensureLoggedIn(page, request);
    await seedE2eProvidersFromEnv(request);

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /Application error|应用出错了/ })).toHaveCount(0);

    await enableTaskTrackingInDialog(page);

    const query =
      'You MUST use update_execution_checklist_tool. ' +
      'Create a 2-item checklist (both pending), mark item 1 completed, mark item 2 completed. ' +
      'Then reply with exactly: TSM_WEBUI_OK';

    const input = page.getByPlaceholder(/输入消息|Type a message/i);
    await input.fill(query);
    await page.getByRole('button', { name: /^发送$|^Send$/i }).click();

    await expect(page.getByText(/Execution checklist/i)).toBeVisible({ timeout: 180_000 });
    await expect(page.getByText(/TSM_WEBUI_OK/i)).toBeVisible({ timeout: 180_000 });
  });
});
