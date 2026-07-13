import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { DEFAULT_SYSTEM_CONFIG, type SystemConfig } from '@/types/system';
import {
  readTauriSystemConfigCache,
  TAURI_SYSTEM_CONFIG_CACHE_KEY,
} from '@/lib/tauri-system-config-cache';

const { mockInvoke } = vi.hoisted(() => ({
  mockInvoke: vi.fn(),
}));

let mockIsTauri = true;

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauri,
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mockInvoke,
}));

describe('useSystemConfig saveAndRestart', () => {
  beforeEach(() => {
    localStorage.clear();
    mockInvoke.mockReset();
    mockIsTauri = true;

    mockInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === 'load_system_config') {
        return DEFAULT_SYSTEM_CONFIG;
      }
      if (cmd === 'get_current_mode') {
        return 'desktop';
      }
      if (cmd === 'get_local_ip') {
        return '127.0.0.1';
      }
      if (cmd === 'restart_app') {
        const raw = localStorage.getItem(TAURI_SYSTEM_CONFIG_CACHE_KEY);
        expect(raw).not.toBeNull();
        const cached = readTauriSystemConfigCache();
        expect(cached?.enableWebUIMode).toBe(true);
        expect(cached?.apiPort).toBe(25808);
      }
      return undefined;
    });
  });

  it('writes localStorage before restart_app', async () => {
    const { useSystemConfig } = await import('@/hooks/useSystemConfig');
    const { result } = renderHook(() => useSystemConfig());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    const nextConfig: SystemConfig = {
      ...DEFAULT_SYSTEM_CONFIG,
      enableWebUIMode: true,
      apiPort: 25808,
    };

    await act(async () => {
      await result.current.saveAndRestart(nextConfig);
    });

    expect(mockInvoke).toHaveBeenCalledWith('save_system_config', { config: nextConfig });
    expect(mockInvoke).toHaveBeenCalledWith('restart_app');
  });
});
