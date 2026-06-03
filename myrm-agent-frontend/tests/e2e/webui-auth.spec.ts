import { test, expect } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

test.describe('WebUI local auth', () => {
  test.skip(
    !process.env.PLAYWRIGHT_RUN_WEBUI_E2E,
    'Set PLAYWRIGHT_RUN_WEBUI_E2E=1 with backend on :8080 and frontend on :3000',
  );

  test('setup -> login -> SSE flow', async ({ page, request }) => {
    // 1. Generate setup token using loopback API
    const tokenRes = await request.post(`${apiBase}/webui/auth/generate-setup-token`);
    expect(tokenRes.ok()).toBeTruthy();
    const tokenData = await tokenRes.json();
    const tempToken = tokenData.temp_token;

    // 2. Visit setup page
    await page.goto(`/auth/setup?token=${tempToken}`);
    await expect(page.locator('text=Admin Setup')).toBeVisible();

    // 3. Fill setup form
    await page.fill('input[type="password"]', 'playwright1234');
    await page.fill('input[name="confirmPassword"]', 'playwright1234');
    await page.click('button[type="submit"]');

    // Wait for setup to complete, which should set the cookie and redirect to login or home
    await page.waitForURL('**/');
    
    // 4. Force navigation to login to test login flow
    await page.request.post(`${apiBase}/webui/auth/logout`);
    
    // Open login page
    await page.goto('/auth/login');
    await expect(page.locator('input[type="password"]')).toBeVisible();

    // 5. Fill login form
    await page.fill('input[type="password"]', 'playwright1234');
    await page.click('button[type="submit"]');

    // Should redirect to home
    await page.waitForURL('**/');

    // 6. Verify SSE API call can be made (using credentials: include)
    // We do this by checking if the UI can load without getting 401s on chat API
    // (Assuming the main page calls some status/history API that requires auth)
    await expect(page.locator('text=MyrmAgent')).toBeVisible({ timeout: 10000 });
  });
});
