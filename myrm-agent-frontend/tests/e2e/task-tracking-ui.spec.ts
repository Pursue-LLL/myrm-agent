import { test, expect } from '@playwright/test';

import { ensureLoggedIn } from './helpers/auth';

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

    // Dismiss optional migration / onboarding banners that intercept clicks.
    await page.getByRole('button', { name: /稍后再说|Later/i }).click({ timeout: 3_000 }).catch(() => {});

    await page.getByRole('button', { name: /内置工具|Built-in [Tt]ools/ }).click({ timeout: 20_000 });
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 10_000 });
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
});
