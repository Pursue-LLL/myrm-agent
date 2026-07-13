import { describe, it, expect, beforeEach } from 'vitest';
import { DEFAULT_SYSTEM_CONFIG, type SystemConfig } from '@/types/system';
import {
  persistTauriSystemConfigCache,
  readTauriSystemConfigCache,
  TAURI_SYSTEM_CONFIG_CACHE_KEY,
} from '@/lib/tauri-system-config-cache';

describe('tauri-system-config-cache', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('persists and reads round-trip config', () => {
    const config: SystemConfig = {
      ...DEFAULT_SYSTEM_CONFIG,
      enableWebUIMode: true,
      apiPort: 25808,
      webuiPort: 3001,
    };

    persistTauriSystemConfigCache(config);

    expect(localStorage.getItem(TAURI_SYSTEM_CONFIG_CACHE_KEY)).toBe(JSON.stringify(config));
    expect(readTauriSystemConfigCache()).toEqual(config);
  });

  it('returns null when cache is missing', () => {
    expect(readTauriSystemConfigCache()).toBeNull();
  });
});
