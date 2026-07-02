import { expect, type APIRequestContext, type Page } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

/** Skip first-run onboarding wizard so chat routes render MessageInput. */
export async function completeOnboardingForE2e(request: APIRequestContext): Promise<void> {
  const readinessRes = await request.get(`${apiBase}/api/v1/config/readiness`, { timeout: 30_000 });
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

  const loginRes = await request.post(`${apiBase}/webui/auth/login`, {
    data: { username: 'admin', password: adminPassword },
  });
  expect(loginRes.ok()).toBeTruthy();
}
