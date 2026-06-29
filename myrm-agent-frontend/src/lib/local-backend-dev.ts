/**
 * [INPUT]
 * - `@/lib/backend-health` (`fetchBackendHealth`, `BackendHealthPayload`)
 *
 * [OUTPUT]
 * - `BOOT_SCREEN_STORAGE_KEY` / `isBootSessionCompleted`: Boot session SSOT
 * - `formatLocalBackendSetupHint` / `resolveLocalBackendSetupHint`: health-aware local setup hints
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
