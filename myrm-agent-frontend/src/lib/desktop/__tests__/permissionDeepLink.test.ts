/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getMacOsAccessibilityGuideFallbackUrl,
  getPermissionGuideFallbackUrl,
  isSystemSettingsDeepLink,
  openPermissionDeepLink,
  openPermissionDeepLinkWithGuideFallback,
  pickSettingsDeepLink,
  pickSettingsDeepLinkFromMeta,
} from '../permissionDeepLink';

const ACCESSIBILITY_DEEPLINK =
  'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility';

vi.mock('@tauri-apps/plugin-shell', () => ({
  open: vi.fn(() => Promise.resolve()),
}));

describe('permissionDeepLink', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('picks accessibility before screen_recording', () => {
    expect(
      pickSettingsDeepLink({
        screen_recording: 'ms-settings:privacy-screen',
        accessibility: ACCESSIBILITY_DEEPLINK,
      }),
    ).toBe(ACCESSIBILITY_DEEPLINK);
  });

  it('reads settings_deeplinks from doctor meta', () => {
    expect(
      pickSettingsDeepLinkFromMeta({
        settings_deeplinks: { accessibility: ACCESSIBILITY_DEEPLINK },
      }),
    ).toBe(ACCESSIBILITY_DEEPLINK);
  });

  it('detects system settings deeplinks', () => {
    expect(isSystemSettingsDeepLink(ACCESSIBILITY_DEEPLINK)).toBe(true);
    expect(isSystemSettingsDeepLink('https://example.com')).toBe(false);
  });

  it('maps platform to guide URL without darwin/win32 substring collision', () => {
    expect(getPermissionGuideFallbackUrl('darwin')).toBe(getMacOsAccessibilityGuideFallbackUrl());
    expect(getPermissionGuideFallbackUrl('win32')).toBe(getPermissionGuideFallbackUrl('windows'));
    expect(getPermissionGuideFallbackUrl('win32')).not.toBe(getMacOsAccessibilityGuideFallbackUrl());
  });

  it('opens system deeplink via tauri shell', async () => {
    const { open } = await import('@tauri-apps/plugin-shell');
    openPermissionDeepLink(ACCESSIBILITY_DEEPLINK);
    await vi.waitFor(() => {
      expect(open).toHaveBeenCalledWith(ACCESSIBILITY_DEEPLINK);
    });
  });

  it('falls back to Apple guide when tauri open fails', async () => {
    const windowOpen = vi.spyOn(window, 'open').mockImplementation(() => null);
    const { open } = await import('@tauri-apps/plugin-shell');
    vi.mocked(open).mockRejectedValueOnce(new Error('not tauri'));

    openPermissionDeepLinkWithGuideFallback(ACCESSIBILITY_DEEPLINK, 'darwin');
    await vi.waitFor(() => {
      expect(windowOpen).toHaveBeenCalledWith(getMacOsAccessibilityGuideFallbackUrl(), '_blank');
    });
    windowOpen.mockRestore();
  });

  it('falls back to Windows guide when platform is win32', async () => {
    const windowOpen = vi.spyOn(window, 'open').mockImplementation(() => null);
    const { open } = await import('@tauri-apps/plugin-shell');
    vi.mocked(open).mockRejectedValueOnce(new Error('not tauri'));

    openPermissionDeepLinkWithGuideFallback('ms-settings:privacy-accessibility', 'win32');
    await vi.waitFor(() => {
      expect(windowOpen).toHaveBeenCalledWith(getPermissionGuideFallbackUrl('win32'), '_blank');
    });
    windowOpen.mockRestore();
  });
});
