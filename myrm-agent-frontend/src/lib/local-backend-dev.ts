/**
 * [INPUT]
 * - `@/lib/backend-health` (`fetchBackendHealth`, `BackendHealthPayload`)
 * - `#locales/en.json` / `zh.json` (`common.configLoadError` — api 层 SSOT；de/ja/ko 回退 en，Banner 仍走 next-intl 全语言）
 *
 * [OUTPUT]
 * - `BOOT_SCREEN_STORAGE_KEY` / `isBootSessionCompleted`: Boot session SSOT
 * - `formatLocalBackendSetupHint` / `resolveLocalBackendSetupHint`: health-aware local setup hints
 * - `BACKEND_UNREACHABLE_CODE` / `resolveBackendUnreachableMessage`: api 层不可达错误指引（无 next-intl hook）
 *
 * [POS]
 * Local/Tauri WebUI 开发连接体验 SSOT：Boot 复访判定与后端 setup 指引（与 Settings ConfigLoadError 一致）。
 */
import enMessages from '#locales/en.json';
import zhMessages from '#locales/zh.json';
import { fetchBackendHealth, type BackendHealthPayload } from '@/lib/backend-health';

export const BOOT_SCREEN_STORAGE_KEY = 'myrm_boot_shown';

export type LocalBackendSetupHintTranslator = (
  key: string,
  values?: Record<string, string | number>,
) => string;

type ConfigLoadErrorHintKey = 'hintUnreachable' | 'hintSplitDev' | 'hintStandalone';

type ConfigLoadErrorMessages = Record<ConfigLoadErrorHintKey, string>;

const LOCALE_HINTS: Record<string, ConfigLoadErrorMessages> = {
  en: enMessages.common.configLoadError,
  zh: zhMessages.common.configLoadError,
};

export function isBootSessionCompleted(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    return sessionStorage.getItem(BOOT_SCREEN_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export function formatLocalBackendSetupHint(
  t: LocalBackendSetupHintTranslator,
  health: BackendHealthPayload | null,
): string {
  if (health?.status === 'healthy' && health.listen_port != null) {
    const host = health.listen_host ?? '127.0.0.1';
    const apiPort = health.backend_port ?? health.listen_port;
    if (health.dev_mode === 'standalone_webui') {
      return t('hintStandalone', {
        host,
        port: health.listen_port,
        proxyPort: apiPort,
      });
    }
    return t('hintSplitDev', {
      host,
      port: health.listen_port,
      proxyPort: apiPort,
    });
  }

  return t('hintUnreachable');
}

export async function resolveLocalBackendSetupHint(
  t: LocalBackendSetupHintTranslator,
): Promise<string> {
  const health = await fetchBackendHealth();
  return formatLocalBackendSetupHint(t, health);
}

/** Structured business code when local backend is unreachable (Next proxy 500 / health probe fail). */
export const BACKEND_UNREACHABLE_CODE = 'BACKEND_UNREACHABLE';

function resolveHintLocale(): string {
  if (typeof navigator === 'undefined') {
    return 'en';
  }
  const lang = navigator.language.toLowerCase();
  if (lang.startsWith('zh')) return 'zh';
  return 'en';
}

function interpolateHint(template: string, values?: Record<string, string | number>): string {
  if (!values) {
    return template;
  }
  return Object.entries(values).reduce(
    (text, [key, value]) => text.replaceAll(`{${key}}`, String(value)),
    template,
  );
}

function createLocaleHintTranslator(locale: string): LocalBackendSetupHintTranslator {
  const messages = LOCALE_HINTS[locale] ?? LOCALE_HINTS.en;
  return (key, values) => {
    const template = messages[key as ConfigLoadErrorHintKey] ?? LOCALE_HINTS.en[key as ConfigLoadErrorHintKey] ?? key;
    return interpolateHint(template, values);
  };
}

/** Health-aware setup hint without next-intl hooks (api layer / toasts). */
export async function resolveBackendUnreachableMessage(): Promise<string> {
  const health = await fetchBackendHealth();
  return formatLocalBackendSetupHint(createLocaleHintTranslator(resolveHintLocale()), health);
}
