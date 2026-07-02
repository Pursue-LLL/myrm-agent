import { expect, type Page } from '@playwright/test';

function adminPassword(): string {
  return process.env.PLAYWRIGHT_ADMIN_PASSWORD ?? 'Playwright1234!';
}

/**
 * Sync httpOnly auth cookies + onboarding on the Playwright page origin (:3000).
 * APIRequestContext login alone does not satisfy Next.js rewrites in the browser.
 */
export async function ensureWebUiBrowserSession(page: Page): Promise<void> {
  const password = adminPassword();
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

  const onboardingOk = await page.evaluate(async () => {
    const readiness = await fetch('/api/v1/config/readiness', { credentials: 'include' });
    if (readiness.ok) {
      const json = (await readiness.json()) as { onboarding_completed?: boolean };
      if (json.onboarding_completed) {
        return true;
      }
    }
    const res = await fetch('/api/v1/config/onboarding/complete', {
      method: 'POST',
      credentials: 'include',
    });
    return res.ok;
  });
  expect(onboardingOk, 'Browser-origin onboarding complete failed').toBeTruthy();

  await page.reload({ waitUntil: 'load' });
}
