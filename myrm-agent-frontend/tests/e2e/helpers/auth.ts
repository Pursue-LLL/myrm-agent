import { expect, type APIRequestContext, type Page } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

/** Skip first-run onboarding wizard so chat routes render MessageInput. */
export async function completeOnboardingForE2e(request: APIRequestContext): Promise<void> {
  const res = await request.post(`${apiBase}/api/v1/config/onboarding/complete`);
  expect(res.ok(), `POST /config/onboarding/complete failed: ${await res.text()}`).toBeTruthy();
}

export async function ensureLoggedIn(page: Page, request: APIRequestContext): Promise<void> {
  const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD ?? 'Playwright1234!';

  const statusRes = await request.get(`${apiBase}/webui/auth/status`);
  expect(statusRes.ok()).toBeTruthy();
  const status = (await statusRes.json()) as { is_setup_done: boolean; is_authenticated: boolean };

  if (!status.is_setup_done) {
    const tokenRes = await request.post(`${apiBase}/webui/auth/generate-setup-token`);
    expect(tokenRes.ok()).toBeTruthy();
    const { temp_token: tempToken } = (await tokenRes.json()) as { temp_token: string };

    await page.goto(`/auth/setup?token=${tempToken}`, { waitUntil: 'domcontentloaded' });
    await page.getByPlaceholder(/Enter your password|输入您的密码/).first().fill(adminPassword);
    await page.getByPlaceholder(/Re-enter your password|重新输入您的密码/).fill(adminPassword);
    await page.getByRole('button', { name: /Set [Pp]assword|设置密码/ }).click();
    await page.waitForURL((url) => !url.pathname.includes('/auth/setup'), { timeout: 15_000 });
    return;
  }

  // Always login on the APIRequestContext so config/agent APIs share the session cookie.
  const loginRes = await request.post(`${apiBase}/webui/auth/login`, {
    data: { username: 'admin', password: adminPassword },
  });
  expect(loginRes.ok()).toBeTruthy();

  await syncBrowserAuthSession(page, adminPassword);
}

/** Login on the Playwright page origin so httpOnly cookies work with Next.js API rewrites (:3000). */
async function syncBrowserAuthSession(page: Page, adminPassword: string): Promise<void> {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const loginOk = await page.evaluate(async (password: string) => {
    const res = await fetch('/webui/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username: 'admin', password }),
    });
    if (!res.ok) {
      return false;
    }
    localStorage.setItem('auth_token', 'local_user_token');
    localStorage.setItem(
      'auth_user',
      JSON.stringify({
        id: 'local-user',
        email: 'local@tauri.app',
        display_name: 'admin',
        role: 'admin',
      }),
    );
    return true;
  }, adminPassword);
  expect(loginOk, 'Browser-origin /webui/auth/login failed').toBeTruthy();

  const onboardingOk = await page.evaluate(async () => {
    const res = await fetch('/api/v1/config/onboarding/complete', {
      method: 'POST',
      credentials: 'include',
    });
    return res.ok;
  });
  expect(onboardingOk, 'Browser-origin onboarding complete failed').toBeTruthy();

  await expect(page.getByRole('button', { name: /新对话|New chat|New Chat/i })).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('textarea[data-chat-input]')).toBeVisible({ timeout: 60_000 });
}
