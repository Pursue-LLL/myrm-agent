/**
 * [INPUT]
 * - @tauri-apps/plugin-shell (POS: Tauri 桌面端打开系统 URL)
 *
 * [OUTPUT]
 * - pickSettingsDeepLink / pickSettingsDeepLinkFromMeta: 从 probe meta 选取 OS 设置深链
 * - openPermissionDeepLink: 打开 OS 设置深链（Tauri shell；失败时 window.open 同一 URL）
 * - openPermissionDeepLinkWithGuideFallback: 同上；失败时打开平台 Accessibility 指南（Web 浏览器场景）
 * - getPermissionGuideFallbackUrl: 按 platform 返回指南 URL（darwin / win32 / linux）
 * - isSystemSettingsDeepLink: 判断是否为 OS 设置 URL
 *
 * [POS]
 * 桌面权限引导深链 SSOT。Doctor / Settings / Agent inline / Inspector 共用同一 pick/open 语义。
 */

const MACOS_ACCESSIBILITY_GUIDE_URL =
  'https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac';

const WINDOWS_ACCESSIBILITY_GUIDE_URL =
  'https://support.microsoft.com/windows/accessibility';

const LINUX_ACCESSIBILITY_GUIDE_URL =
  'https://wiki.gnome.org/Accessibility';

export function getPermissionGuideFallbackUrl(platform?: string | null): string {
  const normalized = (platform ?? '').toLowerCase();
  if (normalized === 'win32' || normalized === 'windows') {
    return WINDOWS_ACCESSIBILITY_GUIDE_URL;
  }
  if (normalized === 'linux') {
    return LINUX_ACCESSIBILITY_GUIDE_URL;
  }
  return MACOS_ACCESSIBILITY_GUIDE_URL;
}

export function isSystemSettingsDeepLink(url: string): boolean {
  return url.startsWith('x-apple.systempreferences:') || url.startsWith('ms-settings:');
}

export function pickSettingsDeepLink(
  deeplinks: Record<string, string> | null | undefined,
): string | null {
  if (!deeplinks) return null;
  return deeplinks.accessibility || deeplinks.screen_recording || null;
}

export function pickSettingsDeepLinkFromMeta(
  meta: Record<string, unknown> | null | undefined,
): string | null {
  if (!meta || typeof meta !== 'object') return null;
  const deeplinks = meta.settings_deeplinks;
  if (!deeplinks || typeof deeplinks !== 'object') return null;
  return pickSettingsDeepLink(deeplinks as Record<string, string>);
}

export function openPermissionDeepLink(url: string): void {
  if (isSystemSettingsDeepLink(url)) {
    import('@tauri-apps/plugin-shell')
      .then((mod) => mod.open(url))
      .catch(() => {
        window.open(url, '_blank');
      });
    return;
  }
  window.open(url, '_blank');
}

export function getMacOsAccessibilityGuideFallbackUrl(): string {
  return MACOS_ACCESSIBILITY_GUIDE_URL;
}

export function openPermissionDeepLinkWithGuideFallback(
  url: string,
  platform?: string | null,
): void {
  import('@tauri-apps/plugin-shell')
    .then((mod) => mod.open(url))
    .catch(() => {
      window.open(getPermissionGuideFallbackUrl(platform), '_blank');
    });
}
