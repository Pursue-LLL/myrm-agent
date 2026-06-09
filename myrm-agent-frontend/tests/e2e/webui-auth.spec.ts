import { test, expect } from '@playwright/test';

import { ensureLoggedIn } from './helpers/auth';

test.describe('WebUI local auth', () => {
  test.skip(
    !process.env.PLAYWRIGHT_RUN_WEBUI_E2E,
    'Set PLAYWRIGHT_RUN_WEBUI_E2E=1 with backend on :8080 and frontend on :3000',
  );

  test('setup or token login -> home and key routes', async ({ page, request }) => {
    await ensureLoggedIn(page, request);

    await expect(page.getByRole('heading', { name: /Application error|应用出错了/ })).toHaveCount(0);

    const protectedRoutes = [
      '/',
      '/chat',
      '/health',
      '/settings',
      '/settings/preferences',
      '/agents',
      '/workspace',
      '/library',
      '/brain',
      '/eval-lab',
      '/growth',
      '/audit',
      '/security',
      '/artifacts',
      '/batch-optimization',
      '/skill-optimization',
    ];

    for (const path of protectedRoutes) {
      await page.goto(path);
      await page.waitForLoadState('domcontentloaded');
      await expect(page.getByRole('heading', { name: /Application error|应用出错了/ })).toHaveCount(0);
    }

    await page.goto('/auth/login');
    await expect(page.getByRole('heading', { name: /Application error|应用出错了/ })).toHaveCount(0);
  });
});
