import { expect, type Page } from '@playwright/test';

/** Call before navigation so the migration banner never blocks send in local mode. */
export async function installMigrationDismissInitScript(page: Page): Promise<void> {
  await page.addInitScript(() => {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
    sessionStorage.setItem('myrm_boot_shown', '1');
  });
}

/** Agent-mode chats use POST /agents/agent-stream; fast search does not. */
export async function ensureAgentMode(page: Page): Promise<void> {
  const agentRadio = page.getByRole('radio', { name: /智能代理|Smart Agent/i });
  if (await agentRadio.isVisible().catch(() => false)) {
    if (!(await agentRadio.isChecked())) {
      await agentRadio.click();
    }
  }
}

export async function prepareChatPageForE2e(page: Page): Promise<void> {
  await page.evaluate(() => {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
    sessionStorage.setItem('myrm_boot_shown', '1');
  });

  const enableFreeSearch = page.getByRole('button', { name: /一键启用免费搜索|Enable free search/i });
  if (await enableFreeSearch.isVisible().catch(() => false)) {
    await enableFreeSearch.click();
  }

  await expect(page.locator('textarea[data-chat-input]')).toBeVisible({ timeout: 60_000 });
  await expect(
    page.getByRole('button', { name: /MiniMax|M2\.7|GPT|Claude|模型|Model/i }).first(),
  ).toBeVisible({
    timeout: 30_000,
  });

  const sendButton = page.locator('button.message-send-btn');
  await expect(sendButton).toBeVisible({ timeout: 15_000 });
}

export async function waitForChatHydration(page: Page, chatId: string): Promise<void> {
  await page
    .waitForResponse(
      (response) => response.url().includes(`/api/v1/chats/${chatId}`) && response.ok(),
      { timeout: 60_000 },
    )
    .catch(() => undefined);
  await expect(page.locator('textarea[data-chat-input]')).toBeEnabled({ timeout: 30_000 });
}

async function collectToastDiagnostics(page: Page): Promise<string> {
  const texts = await page.locator('[data-sonner-toast]').allTextContents();
  const trimmed = texts.map((text) => text.trim()).filter(Boolean);
  return trimmed.length > 0 ? trimmed.join(' | ') : '(no toast visible)';
}

async function assertNoRiskBlockToast(page: Page): Promise<void> {
  const riskToast = page.getByText(/blocked by risk policy|风险策略/i);
  if (await riskToast.isVisible().catch(() => false)) {
    const diagnostics = await collectToastDiagnostics(page);
    throw new Error(`Message blocked by risk policy; toasts: ${diagnostics}`);
  }
}

export async function sendChatMessage(page: Page, message: string): Promise<void> {
  await ensureAgentMode(page);
  const input = page.locator('textarea[data-chat-input]');
  await input.fill(message);
  await expect(page.locator('button.message-send-btn')).toBeEnabled({ timeout: 15_000 });

  const streamResponse = page.waitForResponse(
    (candidate) =>
      candidate.url().includes('agent-stream') && candidate.request().method() === 'POST',
    { timeout: 120_000 },
  );
  await input.press('Enter');

  const response = await streamResponse;
  const body = await response.text();
  if (body.includes('risk_blocked')) {
    const diagnostics = await collectToastDiagnostics(page);
    throw new Error(`agent-stream risk_blocked; toasts: ${diagnostics}; body: ${body.slice(0, 400)}`);
  }
  if (!response.ok()) {
    const diagnostics = await collectToastDiagnostics(page);
    throw new Error(`agent-stream HTTP ${response.status()}; toasts: ${diagnostics}`);
  }

  await assertNoRiskBlockToast(page);
}
