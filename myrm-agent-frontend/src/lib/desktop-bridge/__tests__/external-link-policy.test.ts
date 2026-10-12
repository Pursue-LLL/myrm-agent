/**
 * [INPUT]
 * - @/lib/desktop-bridge (installExternalLinkPolicy, TauriDesktopBridge)
 *
 * [OUTPUT]
 * - Unit tests for the window.open external link policy and its interplay with the Tauri shell bridge
 *
 * [POS]
 * Pins which window.open calls reach the system browser, which stay native, how the policy is removed,
 * and that a refusing shell plugin cannot make one window.open re-enter the bridge.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as tauriModule from '@/lib/tauri';
import { TauriDesktopBridge, installExternalLinkPolicy } from '../index';

const shellOpen = vi.hoisted(() => vi.fn<(url: string) => Promise<void>>());

vi.mock('@tauri-apps/plugin-shell', () => ({ open: shellOpen }));

const PAGE_URL = 'http://127.0.0.1:3777/chat/1';

function createWindow() {
  const nativeOpen = vi.fn<Window['open']>(() => null);
  const win = { open: nativeOpen, location: { href: PAGE_URL } } as unknown as Window;
  const openExternal = vi.fn<(url: string) => Promise<boolean>>(async () => true);
  return { win, nativeOpen, openExternal };
}

interface RoutedCase {
  label: string;
  url: string | URL;
  target: string | undefined;
  expected: string;
}

const ROUTED_CASES: RoutedCase[] = [
  {
    label: 'an explicit _blank target',
    url: 'https://example.com/a?b=1',
    target: '_blank',
    expected: 'https://example.com/a?b=1',
  },
  {
    label: 'an upper-case _BLANK target',
    url: 'https://example.com/',
    target: '_BLANK',
    expected: 'https://example.com/',
  },
  { label: 'an omitted target', url: 'https://example.com/x', target: undefined, expected: 'https://example.com/x' },
  { label: 'an empty target', url: 'https://example.com/x', target: '', expected: 'https://example.com/x' },
  {
    label: 'a page-relative url',
    url: '/api/v1/files/artifacts/7/download',
    target: '_blank',
    expected: 'http://127.0.0.1:3777/api/v1/files/artifacts/7/download',
  },
  { label: 'a protocol-relative url', url: '//example.com/p', target: '_blank', expected: 'http://example.com/p' },
  { label: 'a URL object', url: new URL('https://example.com/u'), target: '_blank', expected: 'https://example.com/u' },
];

interface NativeCase {
  label: string;
  url: string | undefined;
  target: string | undefined;
}

const NATIVE_CASES: NativeCase[] = [
  { label: 'a _self target', url: 'https://example.com/', target: '_self' },
  { label: 'a _parent target', url: 'https://example.com/', target: '_parent' },
  { label: 'a _top target', url: 'https://example.com/', target: '_top' },
  { label: 'a named target', url: 'https://example.com/', target: 'preview-frame' },
  { label: 'a mailto url', url: 'mailto:a@b.co', target: '_blank' },
  { label: 'a javascript url', url: 'javascript:alert(1)', target: '_blank' },
  { label: 'a data url', url: 'data:text/html,hi', target: '_blank' },
  { label: 'a blob url', url: 'blob:http://127.0.0.1:3777/abc', target: '_blank' },
  { label: 'an ftp url', url: 'ftp://example.com/f', target: '_blank' },
  { label: 'a file url', url: 'file:///etc/hosts', target: '_blank' },
  { label: 'about:blank', url: 'about:blank', target: '_blank' },
  { label: 'a custom scheme url', url: 'cursor://file/x', target: '_blank' },
  {
    label: 'a system settings deep link',
    url: 'x-apple.systempreferences:com.apple.preference.security',
    target: '_blank',
  },
  { label: 'an unparseable url', url: 'http://', target: '_blank' },
  { label: 'an omitted url', url: undefined, target: '_blank' },
  { label: 'an empty url', url: '', target: '_blank' },
];

describe('installExternalLinkPolicy', () => {
  it.each(ROUTED_CASES)('hands $label to the system browser and returns null', ({ url, target, expected }) => {
    const { win, nativeOpen, openExternal } = createWindow();
    installExternalLinkPolicy(win, openExternal);

    const result = win.open(url, target, 'noopener,noreferrer');

    expect(result).toBeNull();
    expect(openExternal).toHaveBeenCalledExactlyOnceWith(expected);
    expect(nativeOpen).not.toHaveBeenCalled();
  });

  it.each(NATIVE_CASES)('leaves $label to the native implementation untouched', ({ url, target }) => {
    const { win, nativeOpen, openExternal } = createWindow();
    const nativeResult = { closed: false } as unknown as WindowProxy;
    nativeOpen.mockReturnValue(nativeResult);
    installExternalLinkPolicy(win, openExternal);

    const result = win.open(url, target, 'width=1');

    expect(result).toBe(nativeResult);
    expect(nativeOpen).toHaveBeenCalledExactlyOnceWith(url, target, 'width=1');
    expect(openExternal).not.toHaveBeenCalled();
  });

  it('leaves an argument-less window.open() to the native implementation', () => {
    const { win, nativeOpen, openExternal } = createWindow();
    installExternalLinkPolicy(win, openExternal);

    win.open();

    expect(nativeOpen).toHaveBeenCalledTimes(1);
    expect(openExternal).not.toHaveBeenCalled();
  });

  it('uninstall restores the exact native function', () => {
    const { win, nativeOpen, openExternal } = createWindow();
    const uninstall = installExternalLinkPolicy(win, openExternal);
    expect(win.open).not.toBe(nativeOpen);

    uninstall();

    expect(win.open).toBe(nativeOpen);
  });

  it('survives the React StrictMode install, uninstall, install sequence', () => {
    const { win, nativeOpen, openExternal } = createWindow();
    installExternalLinkPolicy(win, openExternal)();
    const uninstall = installExternalLinkPolicy(win, openExternal);

    win.open('https://example.com/s', '_blank');
    expect(openExternal).toHaveBeenCalledTimes(1);

    uninstall();
    expect(win.open).toBe(nativeOpen);
  });

  it('does not clobber a wrapper that someone else installed on top of it', () => {
    const { win, openExternal } = createWindow();
    const uninstall = installExternalLinkPolicy(win, openExternal);
    const policyOpen = win.open;
    const thirdPartyWrapper = vi.fn<Window['open']>((...args) => policyOpen.apply(win, args));
    win.open = thirdPartyWrapper;

    uninstall();

    expect(win.open).toBe(thirdPartyWrapper);
    win.open('https://example.com/still-routed', '_blank');
    expect(openExternal).toHaveBeenCalledExactlyOnceWith('https://example.com/still-routed');
  });
});

describe('external link policy on top of the Tauri shell bridge', () => {
  const nativeOpen = vi.fn<Window['open']>(() => null);
  const originalOpen = window.open;
  let uninstall: () => void;

  beforeEach(() => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    shellOpen.mockReset();
    nativeOpen.mockClear();
    window.open = nativeOpen;
    const bridge = new TauriDesktopBridge();
    uninstall = installExternalLinkPolicy(window, (url) => bridge.shell.openExternalUrl(url));
  });

  afterEach(() => {
    uninstall();
    window.open = originalOpen;
    vi.restoreAllMocks();
  });

  it('sends a window.open request through the shell plugin and returns null', async () => {
    shellOpen.mockResolvedValue(undefined);

    const result = window.open('https://example.com/docs', '_blank', 'noopener,noreferrer');

    expect(result).toBeNull();
    await vi.waitFor(() => expect(shellOpen).toHaveBeenCalledExactlyOnceWith('https://example.com/docs'));
    expect(nativeOpen).not.toHaveBeenCalled();
  });

  it('makes exactly one plugin attempt per window.open while the plugin keeps refusing', async () => {
    // Refusals stop after a bound so a regression fails the assertion instead of hanging the runner.
    const REFUSAL_BOUND = 50;
    let attempts = 0;
    shellOpen.mockImplementation(async () => {
      attempts += 1;
      if (attempts < REFUSAL_BOUND) {
        throw new Error('url not allowed');
      }
    });

    window.open('https://example.com/x', '_blank');
    await vi.waitFor(() => expect(shellOpen).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(shellOpen).toHaveBeenCalledTimes(1);
    expect(nativeOpen).not.toHaveBeenCalled();
  });
});
