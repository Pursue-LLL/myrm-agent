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

import { ask } from '@tauri-apps/plugin-dialog';
import { readText as tauriReadText } from '@tauri-apps/plugin-clipboard-manager';
import de from '../../../../locales/de.json';
import en from '../../../../locales/en.json';
import ja from '../../../../locales/ja.json';
import ko from '../../../../locales/ko.json';
import zhTW from '../../../../locales/zh-TW.json';
import zh from '../../../../locales/zh.json';
import { readFromClipboard, writeToClipboard } from '../clipboardUtils';

// The global test setup replaces next-intl, so the real translator is loaded explicitly: shipped copy, real ICU.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');
const locales = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;
const PERMISSION_KEY = 'myrm_clipboard_read_permission';

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

describe('clipboardUtils read-permission dialog', () => {
  beforeEach(() => {
    vi.mocked(ask).mockClear();
    vi.mocked(tauriReadText).mockClear();
    sonner.toast.error.mockClear();
    localStorage.clear();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
    vi.restoreAllMocks();
  });

  it('browser: asks with the translated prompt and remembers an allow', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    stubClipboard({ readText: vi.fn().mockResolvedValue('pasted') });

    await expect(readFromClipboard()).resolves.toBe('pasted');

    expect(confirmSpy).toHaveBeenCalledWith('common.clipboard.readPermissionPrompt');
    expect(localStorage.getItem(PERMISSION_KEY)).toBe('granted');
  });

  it('browser: a decline reads nothing, says so, and is not remembered', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const readText = vi.fn();
    stubClipboard({ readText });

    await expect(readFromClipboard()).rejects.toThrow('Permission denied');

    expect(readText).not.toHaveBeenCalled();
    expect(sonner.toast.error).toHaveBeenCalledWith('common.clipboard.readRefused');
    expect(localStorage.getItem(PERMISSION_KEY)).toBeNull();
  });

  it('desktop: the native dialog gets translated title, prompt with remember note, and button labels', async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    vi.mocked(ask).mockResolvedValue(true);
    vi.mocked(tauriReadText).mockResolvedValue('from tauri');

    await expect(readFromClipboard()).resolves.toBe('from tauri');

    expect(ask).toHaveBeenCalledWith(
      'common.clipboard.readPermissionPrompt\n\ncommon.clipboard.readPermissionRemember',
      {
        title: 'common.clipboard.readPermissionTitle',
        kind: 'info',
        okLabel: 'common.clipboard.readPermissionAllow',
        cancelLabel: 'common.clipboard.readPermissionDeny',
      },
    );
    expect(localStorage.getItem(PERMISSION_KEY)).toBe('granted');
  });

  it('desktop: a decline in the native dialog reads nothing and is not remembered', async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    vi.mocked(ask).mockResolvedValue(false);

    await expect(readFromClipboard()).rejects.toThrow('Permission denied');

    expect(tauriReadText).not.toHaveBeenCalled();
    expect(sonner.toast.error).toHaveBeenCalledWith('common.clipboard.readRefused');
    expect(localStorage.getItem(PERMISSION_KEY)).toBeNull();
  });
});

describe('clipboard read-permission copy in every locale', () => {
  it.each(Object.entries(locales))('%s: every dialog string resolves to real copy', (locale, messages) => {
    const t = createTranslator({ locale, messages, namespace: 'common.clipboard' });

    for (const key of [
      'readPermissionTitle',
      'readPermissionPrompt',
      'readPermissionRemember',
      'readPermissionAllow',
      'readPermissionDeny',
    ] as const) {
      expect(t(key).trim()).not.toBe('');
      expect(t(key)).not.toContain('common.clipboard');
    }
  });
});
