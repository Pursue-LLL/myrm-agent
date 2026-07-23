/**
 * [INPUT]
 * @/lib/deploy-mode::isLocalMode (POS: local vs cloud deploy mode)
 * @/services/i18nToastService::translateI18nKey (POS: store-safe i18n lookup)
 *
 * [OUTPUT]
 * SEARCH_SETTINGS_PATH, resolveWebSearchConfigGapActionLabel, runWebSearchConfigGapAction
 *
 * [POS]
 * SSOT for web search config-gap CTA (SSE toast + fast/deep guard). Keeps gapEvents free
 * of static useConfigStore imports for testability.
 */

import { isLocalMode } from '@/lib/deploy-mode';
import { translateI18nKey } from '@/services/i18nToastService';

/** Default settings path for search service configuration. */
export const SEARCH_SETTINGS_PATH = '/settings/search';

const SEARCH_GAP_CTA_KEYS = {
  settings: 'chat.searchNotConfigured.action',
  localEnable: 'chat.searchNotConfigured.enableAction',
} as const;

/** i18n key for web search config-gap CTA (shared with showSearchNotConfiguredToast). */
export function resolveWebSearchConfigGapActionLabelKey(): string {
  return isLocalMode() ? SEARCH_GAP_CTA_KEYS.localEnable : SEARCH_GAP_CTA_KEYS.settings;
}

/**
 * Resolve CTA label for web search config gap (SSE toast + fast/deep guard).
 * Uses document lang when isZh is omitted.
 */
export function resolveWebSearchConfigGapActionLabel(isZh?: boolean): string {
  const zh = isZh ?? (typeof document !== 'undefined' && document.documentElement.lang.startsWith('zh'));
  const key = resolveWebSearchConfigGapActionLabelKey();
  const fallbacks: Record<string, string> = {
    [SEARCH_GAP_CTA_KEYS.settings]: zh ? '前往设置' : 'Go to Settings',
    [SEARCH_GAP_CTA_KEYS.localEnable]: zh ? '一键启用免费搜索' : 'Enable free search',
  };
  return translateI18nKey(key, fallbacks[key] ?? key);
}

/**
 * Run search config gap CTA: local quick-enable when available, else navigate to settings.
 */
export async function runWebSearchConfigGapAction(
  settingsPath: string = SEARCH_SETTINGS_PATH,
): Promise<void> {
  if (isLocalMode()) {
    const { probeAndBuildQuickSearchConfig } = await import('@/store/config/quickSearchSetup');
    const config = await probeAndBuildQuickSearchConfig();
    if (config) {
      const useConfigStore = (await import('@/store/useConfigStore')).default;
      useConfigStore.getState().addSearchServiceConfig(config);
      return;
    }
  }
  if (typeof window !== 'undefined') {
    window.location.assign(settingsPath);
  }
}
