import type { SystemConfig } from '@/types/system';

export const TAURI_SYSTEM_CONFIG_CACHE_KEY = 'myrm-tauri-system-config';

export function persistTauriSystemConfigCache(config: SystemConfig): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    const storage = window.localStorage;
    if (storage) {
      storage.setItem(TAURI_SYSTEM_CONFIG_CACHE_KEY, JSON.stringify(config));
    }
  } catch {
    // ignore quota / private mode
  }
}

export function readTauriSystemConfigCache(): SystemConfig | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const storage = window.localStorage;
    const raw = storage ? storage.getItem(TAURI_SYSTEM_CONFIG_CACHE_KEY) : null;
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as SystemConfig;
  } catch {
    return null;
  }
}
