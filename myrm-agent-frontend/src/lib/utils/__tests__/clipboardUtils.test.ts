import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const sonner = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('sonner', () => sonner);
vi.mock('@tauri-apps/plugin-clipboard-manager', () => ({
  writeText: vi.fn(),
  readText: vi.fn(),
  writeHtml: vi.fn(),
}));
vi.mock('@tauri-apps/plugin-dialog', () => ({ ask: vi.fn() }));
// No translator exists in unit tests; echoing the key shows which copy each outcome resolves.
vi.mock('@/services/i18nToastService', () => ({
  translateI18nKey: (key: string) => key,
}));

import { readFromClipboard, writeToClipboard } from '../clipboardUtils';

function stubClipboard(clipboard: Partial<Clipboard>) {
  Object.defineProperty(navigator, 'clipboard', { value: clipboard, configurable: true });
}

describe('clipboardUtils toasts', () => {
  beforeEach(() => {
    sonner.toast.success.mockClear();
    sonner.toast.error.mockClear();
    localStorage.clear();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('confirms a successful copy with the translated clipboard message', async () => {
    stubClipboard({ writeText: vi.fn().mockResolvedValue(undefined) });

    await expect(writeToClipboard('hello')).resolves.toBe(true);

    expect(sonner.toast.success).toHaveBeenCalledWith('common.clipboard.copied');
  });

  it('stays silent on request', async () => {
    stubClipboard({ writeText: vi.fn().mockResolvedValue(undefined) });

    await expect(writeToClipboard('hello', true)).resolves.toBe(true);

    expect(sonner.toast.success).not.toHaveBeenCalled();
  });

  it('reports a failed copy with the translated permission hint', async () => {
    stubClipboard({ writeText: vi.fn().mockRejectedValue(new Error('boom')) });

    await expect(writeToClipboard('hello')).resolves.toBe(false);

    expect(sonner.toast.error).toHaveBeenCalledWith('common.clipboard.copyFailed');
  });

  it('explains that clipboard reading was blocked when the user previously denied it', async () => {
    localStorage.setItem('myrm_clipboard_read_permission', 'denied');
    stubClipboard({ readText: vi.fn() });

    await expect(readFromClipboard()).rejects.toThrow('Permission denied');

    expect(sonner.toast.error).toHaveBeenCalledWith('common.clipboard.readBlocked');
    expect(sonner.toast.error).toHaveBeenCalledWith('common.clipboard.readFailed');
  });

  it('reports a read failure with the translated permission hint', async () => {
    localStorage.setItem('myrm_clipboard_read_permission', 'granted');
    stubClipboard({ readText: vi.fn().mockRejectedValue(new Error('boom')) });

    await expect(readFromClipboard()).rejects.toThrow('boom');

    expect(sonner.toast.error).toHaveBeenCalledWith('common.clipboard.readFailed');
  });
});
