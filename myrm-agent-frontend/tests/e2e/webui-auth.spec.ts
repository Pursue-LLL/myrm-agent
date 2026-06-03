import { test, expect } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

test.describe('WebUI local auth', () => {
  test.skip(
    !process.env.PLAYWRIGHT_RUN_WEBUI_E2E,
    'Set PLAYWRIGHT_RUN_WEBUI_E2E=1 with backend on :8080 and frontend on :3000',
  );

  test('setup link page loads', async ({ page }) => {
    const statusRes = await page.request.get(`${apiBase}/webui/auth/status`);
    expect(statusRes.ok()).toBeTruthy();
    await page.goto('/auth/login');
    await expect(page.getByRole('heading')).toBeVisible();
  });
});
