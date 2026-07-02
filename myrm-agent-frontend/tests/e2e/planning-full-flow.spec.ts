import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import { completeOnboardingForE2e, ensureLoggedIn } from './helpers/auth';
import {
  installMigrationDismissInitScript,
  prepareChatPageForE2e,
  sendChatMessage,
} from './helpers/prepareChatPageForE2e';
import { E2E_CONFIG_DEVICE_ID, hasE2eLlmEnv, seedE2eProvidersFromEnv } from './helpers/seedE2eProviders';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

async function enableGoalsFeatureGate(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/api/v1/features', async (route) => {
    const upstream = await route.fetch();
    const json = (await upstream.json()) as { features?: Array<{ id: string; enabled: boolean }> };
    const features = json.features ?? [];
    const goals = features.find((item) => item.id === 'goals_system');
    if (goals) {
      goals.enabled = true;
    } else {
      features.push({ id: 'goals_system', enabled: true });
    }
    await route.fulfill({
      status: upstream.status(),
      contentType: 'application/json',
      body: JSON.stringify({ ...json, features }),
    });
  });
}

function seedWorkspaceTodos(chatId: string): void {
  const harnessDir = process.env.HARNESS_DIR?.trim() || path.join(process.env.HOME ?? '', '.myrm/harness');
  const workspaceRoot = path.join(harnessDir, 'workspaces', `chat_${chatId}`);
  const todosDir = path.join(workspaceRoot, '.myrm', 'progress');
  mkdirSync(todosDir, { recursive: true });
  writeFileSync(
    path.join(todosDir, 'todos.json'),
    JSON.stringify(
      {
        goal: 'UI E2E Plan',
        todos: [
          { id: 'ui_step_a', content: 'Verify sidebar', status: 'pending' },
          { id: 'ui_step_b', content: 'Verify mobile card', status: 'completed' },
        ],
      },
      null,
      2,
    ),
    'utf8',
  );
}

test.describe('Planning full UI flow', () => {
  test.describe.configure({ mode: 'serial', timeout: 180_000 });

  test.skip(
    !process.env.PLAYWRIGHT_RUN_PLANNING_FULL_FLOW || !hasE2eLlmEnv(),
    'Set PLAYWRIGHT_RUN_PLANNING_FULL_FLOW=1 and LLM keys from .env.test with :8080 + :3000',
  );

  test('workspace todos hydrate desktop GoalControlPlane and mobile command center', async ({
    page,
    request,
  }) => {
    await completeOnboardingForE2e(request);
    await seedE2eProvidersFromEnv(request, { force: true, deviceId: E2E_CONFIG_DEVICE_ID });
    await ensureLoggedIn(page, request);
    await enableGoalsFeatureGate(page);

    const chatId = `plan_ui_${Date.now()}`;
    const createRes = await request.post(`${apiBase}/api/v1/chats/`, {
      data: { chat_id: chatId },
      timeout: 60_000,
    });
    expect(createRes.ok()).toBeTruthy();
    seedWorkspaceTodos(chatId);

    const planRes = await request.get(`${apiBase}/api/v1/goals/${chatId}/plan`, { timeout: 30_000 });
    expect(planRes.ok()).toBeTruthy();
    const planPayload = (await planRes.json()) as { plan?: { goal?: string } };
    expect(planPayload.plan?.goal).toBe('UI E2E Plan');

    await installMigrationDismissInitScript(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/${chatId}`, { waitUntil: 'domcontentloaded' });
    await prepareChatPageForE2e(page);

    await sendChatMessage(page, 'Reply OK only.');
    await expect(page.getByText('UI E2E Plan').first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/Verify sidebar|Verify mobile/i).first()).toBeVisible({ timeout: 15_000 });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/mobile/status/${chatId}`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('UI E2E Plan').first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/Verify sidebar|Verify mobile/i).first()).toBeVisible({ timeout: 15_000 });
  });
});
