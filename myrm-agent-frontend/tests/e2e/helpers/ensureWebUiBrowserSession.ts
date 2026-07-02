import { expect, type Page } from '@playwright/test';

import { adminPassword, syncBrowserWebUiSession } from './auth';

/**
 * Sync httpOnly auth cookies + onboarding on the Playwright page origin (:3000).
 * APIRequestContext login alone does not satisfy Next.js rewrites in the browser.
 */
export async function ensureWebUiBrowserSession(page: Page): Promise<void> {
  await syncBrowserWebUiSession(page, adminPassword());

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
