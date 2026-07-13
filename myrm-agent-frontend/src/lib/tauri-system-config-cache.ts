import type { SystemConfig } from '@/types/system';

export const TAURI_SYSTEM_CONFIG_CACHE_KEY = 'myrm-tauri-system-config';

export function persistTauriSystemConfigCache(config: SystemConfig): void {
  try {
    localStorage.setItem(TAURI_SYSTEM_CONFIG_CACHE_KEY, JSON.stringify(config));
  } catch {
    // ignore quota / private mode
  }
}

export function readTauriSystemConfigCache(): SystemConfig | null {
  try {
    const raw = localStorage.getItem(TAURI_SYSTEM_CONFIG_CACHE_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as SystemConfig;
  } catch {
    return null;
  }
}
