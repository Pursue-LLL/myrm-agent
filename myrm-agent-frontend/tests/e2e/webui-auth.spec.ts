import { test, expect } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

test.describe('WebUI local auth', () => {
  test.skip(
    !process.env.PLAYWRIGHT_RUN_WEBUI_E2E,
    'Set PLAYWRIGHT_RUN_WEBUI_E2E=1 with backend on :8080 and frontend on :3000',
  );

  test('setup or token login -> home and key routes', async ({ page, request }) => {
    const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD ?? 'Playwright1234!';

    const statusRes = await request.get(`${apiBase}/webui/auth/status`);
    expect(statusRes.ok()).toBeTruthy();
    const status = (await statusRes.json()) as { is_setup_done: boolean };

    if (!status.is_setup_done) {
      const tokenRes = await request.post(`${apiBase}/webui/auth/generate-setup-token`);
      expect(tokenRes.ok()).toBeTruthy();
      const { temp_token: tempToken } = (await tokenRes.json()) as { temp_token: string };

      await page.goto(`/auth/setup?token=${tempToken}`);
      await expect(page.getByRole('heading', { name: /Set Up Admin Account|设置管理员账户/ })).toBeVisible();

      await page.getByPlaceholder(/Enter your password|输入您的密码/).first().fill(adminPassword);
      await page.getByPlaceholder(/Re-enter your password|重新输入您的密码/).fill(adminPassword);
      await page.getByRole('button', { name: /Set [Pp]assword|设置密码/ }).click();

      await page.waitForURL((url) => !url.pathname.includes('/auth/setup'), { timeout: 15_000 });
    } else {
      await request.post(`${apiBase}/webui/auth/logout`);

      const tokenRes = await request.post(`${apiBase}/webui/auth/generate-setup-token`);
      expect(tokenRes.ok()).toBeTruthy();
      const { temp_token: tempToken } = (await tokenRes.json()) as { temp_token: string };

      await page.goto(`/auth/login?token=${encodeURIComponent(tempToken)}`);
      await page.waitForURL((url) => url.pathname === '/' || url.pathname === '', { timeout: 30_000 });
    }

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
