import { expect, type APIRequestContext, type Page } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

export function adminPassword(): string {
  return process.env.PLAYWRIGHT_ADMIN_PASSWORD ?? 'Playwright1234!';
}

/** Sync httpOnly cookies + localStorage on the Playwright page origin (:3000). */
export async function syncBrowserWebUiSession(page: Page, password: string = adminPassword()): Promise<void> {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const loginOk = await page.evaluate(async (pwd: string) => {
    const res = await fetch('/webui/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username: 'admin', password: pwd }),
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
  }, password);
  expect(loginOk, 'Browser-origin /webui/auth/login failed').toBeTruthy();
  await page.reload({ waitUntil: 'domcontentloaded' });
}

/** Skip first-run onboarding wizard so chat routes render MessageInput. */
export async function completeOnboardingForE2e(request: APIRequestContext): Promise<void> {
  const readinessRes = await request.get(`${apiBase}/api/v1/config/readiness`, { timeout: 60_000 });
  if (readinessRes.ok()) {
    const readiness = (await readinessRes.json()) as { onboarding_completed?: boolean };
    if (readiness.onboarding_completed) {
      return;
    }
  }

  const res = await request.post(`${apiBase}/api/v1/config/onboarding/complete`, { timeout: 120_000 });
  expect(res.ok(), `POST /config/onboarding/complete failed: ${await res.text()}`).toBeTruthy();
}

/** APIRequestContext session for backend config/agent calls. Does not sync browser cookies. */
export async function ensureLoggedIn(page: Page, request: APIRequestContext): Promise<void> {
  const password = adminPassword();

  const statusRes = await request.get(`${apiBase}/webui/auth/status`);
  expect(statusRes.ok()).toBeTruthy();
  const status = (await statusRes.json()) as { is_setup_done: boolean; is_authenticated: boolean };

  if (!status.is_setup_done) {
    const tokenRes = await request.post(`${apiBase}/webui/auth/generate-setup-token`);
    expect(tokenRes.ok()).toBeTruthy();
    const { temp_token: tempToken } = (await tokenRes.json()) as { temp_token: string };

    await page.goto(`/auth/setup?token=${tempToken}`, { waitUntil: 'domcontentloaded' });
    await page.getByPlaceholder(/Enter your password|输入您的密码/).first().fill(password);
    await page.getByPlaceholder(/Re-enter your password|重新输入您的密码/).fill(password);
    await page.getByRole('button', { name: /Set [Pp]assword|设置密码/ }).click();
    await page.waitForURL((url) => !url.pathname.includes('/auth/setup'), { timeout: 15_000 });
    return;
  }

  const loginRes = await request.post(`${apiBase}/webui/auth/login`, {
    data: { username: 'admin', password },
  });
  expect(loginRes.ok()).toBeTruthy();
  await syncBrowserWebUiSession(page, password);
}
