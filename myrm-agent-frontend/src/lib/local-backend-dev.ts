/**
 * [INPUT]
 * - `@/lib/backend-health` (`fetchBackendHealth`, `BackendHealthPayload`)
 *
 * [OUTPUT]
 * - `BOOT_SCREEN_STORAGE_KEY` / `isBootSessionCompleted`: Boot session SSOT
 * - `formatLocalBackendSetupHint` / `resolveLocalBackendSetupHint`: health-aware local setup hints
 * - `BACKEND_UNREACHABLE_CODE` / `resolveBackendUnreachableMessage`: api 层不可达错误指引（无 next-intl）
 *
 * [POS]
 * Local/Tauri WebUI 开发连接体验 SSOT：Boot 复访判定与后端 setup 指引（与 Settings ConfigLoadError 一致）。
 */
import { fetchBackendHealth, type BackendHealthPayload } from '@/lib/backend-health';

export const BOOT_SCREEN_STORAGE_KEY = 'myrm_boot_shown';

export type LocalBackendSetupHintTranslator = (
  key: string,
  values?: Record<string, string | number>,
) => string;

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
    const proxy = health.frontend_proxy_port ?? health.listen_port;
    if (health.dev_mode === 'standalone_webui') {
      return t('hintStandalone', {
        host,
        port: health.listen_port,
        proxyPort: proxy,
      });
    }
    return t('hintSplitDev', {
      host,
      port: health.listen_port,
      proxyPort: proxy,
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

type HintLocale = 'en' | 'zh';

const HINT_MESSAGES: Record<HintLocale, Record<string, string>> = {
  en: {
    hintUnreachable:
      'Backend not reachable. Run: myrm dev or myrm start. Ensure .env.local has API_PORT=8080.',
    hintSplitDev:
      'Backend OK at http://{host}:{port}. Run myrm start, or bun run dev then open http://localhost:3000 (API_PORT={proxyPort}).',
    hintStandalone:
      'Backend OK at http://{host}:{port}. Run myrm start, or set API_PORT={proxyPort} in .env.local.',
  },
  zh: {
    hintUnreachable:
      '后端未响应。请运行 myrm dev 或 myrm start，并确认 .env.local 含 API_PORT=8080。',
    hintSplitDev:
      '后端已就绪 http://{host}:{port}。请运行 myrm start，或 bun run dev 后访问 http://localhost:3000（API_PORT={proxyPort}）。',
    hintStandalone:
      '后端已就绪 http://{host}:{port}。请运行 myrm start，或在 .env.local 设置 API_PORT={proxyPort}。',
  },
};

function resolveHintLocale(): HintLocale {
  if (typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('zh')) {
    return 'zh';
  }
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

function createFallbackHintTranslator(locale: HintLocale): LocalBackendSetupHintTranslator {
  return (key, values) => {
    const template = HINT_MESSAGES[locale][key] ?? HINT_MESSAGES.en[key] ?? key;
    return interpolateHint(template, values);
  };
}

/** Health-aware setup hint without next-intl (api layer / toasts). */
export async function resolveBackendUnreachableMessage(): Promise<string> {
  const health = await fetchBackendHealth();
  return formatLocalBackendSetupHint(createFallbackHintTranslator(resolveHintLocale()), health);
}
