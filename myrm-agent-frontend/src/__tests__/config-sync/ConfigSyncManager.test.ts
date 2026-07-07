/**
 * ConfigSyncManager 测试
 *
 * 测试配置同步管理器的核心功能
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { DEFAULT_PERSONAL_SETTINGS, type ConfigValueMap } from '@/services/config/types';

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: vi.fn(() => true),
  getApiBaseUrl: vi.fn(() => 'http://localhost:8080/api/v1'),
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(() => Promise.resolve(true)),
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();
Object.defineProperty(global, 'localStorage', { value: localStorageMock });

describe('ConfigSyncManager', () => {
  let manager: ConfigSyncManager;

  const createPersonalSettings = (): ConfigValueMap['personalSettings'] => ({
    ...DEFAULT_PERSONAL_SETTINGS,
    systemInstructions: 'test',
  });

  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
    resetConfigSyncManager();
    manager = new ConfigSyncManager();
  });

  afterEach(() => {
    resetConfigSyncManager();
  });

  describe('初始化', () => {
    it('初始状态应该是 idle', () => {
      expect(manager.status).toBe('idle');
      expect(manager.isInitialized).toBe(false);
    });

    it('初始化成功后状态应该是 idle 且 isInitialized 为 true', async () => {
      // Mock 成功的 API 响应
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ configs: {} }),
      });

      await manager.initialize();

      expect(manager.status).toBe('idle');
      expect(manager.isInitialized).toBe(true);
    });

    it('重复初始化应该返回缓存', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ configs: {} }),
      });

      await manager.initialize();
      await manager.initialize();

      // 只应该调用一次 fetch
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it('后端不可达时应标记 offline 且不请求配置', async () => {
      const { ensureLocalBackendReady } = await import('@/lib/backend-health');
      vi.mocked(ensureLocalBackendReady).mockResolvedValueOnce(false);

      const result = await manager.initialize();

      expect(manager.status).toBe('offline');
      expect(manager.isInitialized).toBe(true);
      expect(result.size).toBe(0);
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('sync 收到 Next 代理 500 时应进入 offline 而非 error', async () => {
      vi.useFakeTimers();

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ configs: {} }),
      });
      await manager.initialize();

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      });

      manager.set('personalSettings', createPersonalSettings());
      await vi.advanceTimersByTimeAsync(1100);

      expect(manager.status).toBe('offline');

      vi.useRealTimers();
    });
  });

  describe('get/set 操作', () => {
    beforeEach(async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ configs: {} }),
      });
      await manager.initialize();
    });

    it('get 应该返回 null 当配置不存在时', () => {
      const result = manager.get('personalSettings');
      expect(result).toBeNull();
    });

    it('set 应该更新缓存', () => {
      const testValue = createPersonalSettings();

      manager.set('personalSettings', testValue);

      const result = manager.get('personalSettings');
      expect(result).toEqual(testValue);
    });

    it('set 应该触发防抖同步', async () => {
      vi.useFakeTimers();

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            conflicts: [],
            newVersions: { personalSettings: '1706000000000_1' },
          }),
      });

      const testValue = createPersonalSettings();

      manager.set('personalSettings', testValue);

      // 防抖时间内不应该调用 fetch
      expect(mockFetch).toHaveBeenCalledTimes(1); // 只有初始化的调用

      // 等待防抖时间
      await vi.advanceTimersByTimeAsync(1100);

      // 应该调用 sync
      expect(mockFetch).toHaveBeenCalledTimes(2);

      vi.useRealTimers();
    });
  });

  describe('订阅功能', () => {
    beforeEach(async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ configs: {} }),
      });
      await manager.initialize();
    });

    it('subscribe 应该在配置变更时通知监听器', () => {
      const listener = vi.fn();
      manager.subscribe('personalSettings', listener);

      const testValue = createPersonalSettings();

      manager.set('personalSettings', testValue);

      expect(listener).toHaveBeenCalledWith(
        'personalSettings',
        testValue,
        expect.objectContaining({
          version: expect.any(String),
          updatedAt: expect.any(String),
          deviceId: expect.any(String),
        }),
      );
    });

    it('取消订阅后不应该收到通知', () => {
      const listener = vi.fn();
      const unsubscribe = manager.subscribe('personalSettings', listener);

      unsubscribe();

      const testValue = createPersonalSettings();

      manager.set('personalSettings', testValue);

      expect(listener).not.toHaveBeenCalled();
    });
  });

  describe('forceSync', () => {
    beforeEach(async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ configs: {} }),
      });
      await manager.initialize();
    });

    it('forceSync 应该立即同步而不等待防抖', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            conflicts: [],
            newVersions: { personalSettings: '1706000000000_1' },
          }),
      });

      const testValue = createPersonalSettings();

      manager.set('personalSettings', testValue);

      const result = await manager.forceSync();

      expect(result.success).toBe(true);
      expect(mockFetch).toHaveBeenCalledTimes(2); // 初始化 + sync
    });
  });
});
