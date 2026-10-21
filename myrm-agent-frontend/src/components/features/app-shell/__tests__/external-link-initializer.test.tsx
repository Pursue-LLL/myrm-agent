/** @vitest-environment jsdom */
import { StrictMode } from 'react';
import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';

import { desktopBridge, type IShellBridge } from '@/lib/desktop-bridge';
import * as tauriModule from '@/lib/tauri';
import ExternalLinkInitializer from '../external-link-initializer';

describe('ExternalLinkInitializer', () => {
  const nativeOpen = vi.fn<Window['open']>(() => null);
  const originalOpen = window.open;
  let openExternalUrl: MockInstance<IShellBridge['openExternalUrl']>;

  beforeEach(() => {
    nativeOpen.mockClear();
    window.open = nativeOpen;
    openExternalUrl = vi.spyOn(desktopBridge.shell, 'openExternalUrl').mockResolvedValue(true);
  });

  afterEach(() => {
    window.open = originalOpen;
    vi.restoreAllMocks();
  });

  it('routes a new-window http(s) request to the system browser inside the Tauri shell', () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
    render(<ExternalLinkInitializer />);

    const result = window.open('https://example.com/docs', '_blank', 'noopener,noreferrer');

    expect(result).toBeNull();
    expect(openExternalUrl).toHaveBeenCalledExactlyOnceWith('https://example.com/docs');
    expect(nativeOpen).not.toHaveBeenCalled();
  });

  it('restores the native window.open on unmount', () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
    const { unmount } = render(<ExternalLinkInitializer />);
    expect(window.open).not.toBe(nativeOpen);

    unmount();

    expect(window.open).toBe(nativeOpen);
  });

  it('installs exactly one policy under React StrictMode double mounting', () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
    const { unmount } = render(
      <StrictMode>
        <ExternalLinkInitializer />
      </StrictMode>,
    );

    window.open('https://example.com/once', '_blank');
    expect(openExternalUrl).toHaveBeenCalledTimes(1);

    unmount();
    expect(window.open).toBe(nativeOpen);
  });

  it('leaves window.open untouched outside the Tauri shell', () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    render(<ExternalLinkInitializer />);

    expect(window.open).toBe(nativeOpen);
    window.open('https://example.com/web', '_blank');
    expect(nativeOpen).toHaveBeenCalledTimes(1);
    expect(openExternalUrl).not.toHaveBeenCalled();
  });
});
