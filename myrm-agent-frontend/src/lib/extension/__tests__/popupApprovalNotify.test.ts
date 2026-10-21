/**
 * Popup toggle for the approval reminder, against the real popup markup.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

const POPUP_HTML = readFileSync(resolve(__dirname, '../../../../../myrm-agent-extension/src/popup.html'), 'utf8');
const POPUP_BODY = /<body>([\s\S]*)<\/body>/.exec(POPUP_HTML)?.[1] ?? '';

const checkbox = () => document.getElementById('approval-notify') as HTMLInputElement;

async function openPopup(stored: Record<string, unknown>) {
  const set = vi.fn();
  vi.stubGlobal('chrome', {
    i18n: { getMessage: (key: string) => key },
    storage: { local: { get: (_keys: string[], callback: (data: object) => void) => callback(stored), set } },
    runtime: { sendMessage: vi.fn() },
  });
  vi.spyOn(globalThis, 'setInterval').mockReturnValue(0 as unknown as ReturnType<typeof setInterval>);
  vi.resetModules();
  document.body.innerHTML = POPUP_BODY;
  await import('../../../../../myrm-agent-extension/src/popup.js');
  return set;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('popup approval reminder toggle', () => {
  it('is on until the user turns it off', async () => {
    await openPopup({});

    expect(checkbox().checked).toBe(true);
  });

  it('shows it off once the user has turned it off', async () => {
    await openPopup({ approvalNotifyEnabled: false });

    expect(checkbox().checked).toBe(false);
  });

  it('saves the choice as soon as it changes', async () => {
    const set = await openPopup({});

    checkbox().checked = false;
    checkbox().dispatchEvent(new Event('change'));
    expect(set).toHaveBeenLastCalledWith({ approvalNotifyEnabled: false });

    checkbox().checked = true;
    checkbox().dispatchEvent(new Event('change'));
    expect(set).toHaveBeenLastCalledWith({ approvalNotifyEnabled: true });
  });
});
