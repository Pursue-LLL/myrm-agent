import { expect, type Page } from '@playwright/test';

export async function dismissOptionalBanners(page: Page): Promise<void> {
  await page.getByRole('button', { name: /稍后再说|Later/i }).click({ timeout: 3_000 }).catch(() => {});
}

export async function openBuiltinToolsDialog(page: Page): Promise<void> {
  await dismissOptionalBanners(page);
  await page.getByRole('button', { name: /内置工具|Built-in [Tt]ools/ }).click({ timeout: 20_000 });
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 10_000 });
}

export async function enableTaskTrackingInDialog(page: Page): Promise<void> {
  await openBuiltinToolsDialog(page);
  await expect(page.getByTestId('builtin-task_tracking')).toBeVisible({ timeout: 10_000 });

  await page.evaluate(() => {
    document.querySelectorAll('[data-radix-scroll-area-viewport]').forEach((viewport) => {
      viewport.scrollTop = viewport.scrollHeight;
    });
  });

  const taskCard = page.getByTestId('builtin-task_tracking');
  await taskCard.evaluate((el) => {
    el.scrollIntoView({ block: 'center', inline: 'nearest' });
    (el as HTMLElement).click();
  });

  const dialog = page.getByRole('dialog');
  const okButton = dialog.getByRole('button', { name: /^(确认|确定|Confirm)$/i });
  await okButton.evaluate((el) => {
    el.scrollIntoView({ block: 'center', inline: 'nearest' });
    (el as HTMLElement).click();
  });
  await expect(dialog).toBeHidden({ timeout: 10_000 });
}
