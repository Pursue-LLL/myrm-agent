import { expect, type Page } from '@playwright/test';

/** Call before navigation so the migration banner never blocks send in local mode. */
export async function installMigrationDismissInitScript(page: Page): Promise<void> {
  await page.addInitScript(() => {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  });
}

export async function prepareChatPageForE2e(page: Page): Promise<void> {
  await page.evaluate(() => {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  });

  await expect(page.locator('textarea[data-chat-input]')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: /MiniMax|M2\.7|GPT|Claude|模型|Model/i })).toBeVisible({
    timeout: 30_000,
  });

  const sendButton = page.locator('button.message-send-btn');
  await expect(sendButton).toBeVisible({ timeout: 15_000 });
  await expect(sendButton).toBeEnabled({ timeout: 15_000 });
}

export async function sendChatMessage(page: Page, message: string): Promise<void> {
  const input = page.locator('textarea[data-chat-input]');
  await input.fill(message);
  await expect(page.locator('button.message-send-btn')).toBeEnabled({ timeout: 15_000 });
  await page.locator('button.message-send-btn').click();
  await expect(input).toHaveValue('', { timeout: 30_000 });
}
