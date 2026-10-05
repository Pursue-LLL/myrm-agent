/**
 * 平台检测测试
 *
 * 测试 Tauri 环境检测功能
 */

import { describe, it, expect, afterEach } from 'vitest';
import { isTauriRuntime } from '@/lib/deploy-mode';

describe('Platform Detection', () => {
  const originalWindow = global.window;

  afterEach(() => {
    global.window = originalWindow;
  });

  describe('isTauriRuntime', () => {
    it('应该在 Tauri 环境中返回 true', () => {
      global.window = Object.assign({}, originalWindow, { __TAURI__: {} });

      expect(isTauriRuntime()).toBe(true);
    });

    it('应该在非 Tauri 环境中返回 false', () => {
      global.window = Object.assign({}, originalWindow);

      delete (global.window as Window & { __TAURI__?: unknown }).__TAURI__;

      expect(isTauriRuntime()).toBe(false);
    });

    it('应该在 window 未定义时返回 false', () => {
      (global as { window?: unknown }).window = undefined;

      expect(isTauriRuntime()).toBe(false);

      global.window = originalWindow;
    });
  });
});
