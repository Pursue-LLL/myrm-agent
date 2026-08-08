/**
 * Vitest测试环境配置
 *
 * 这个文件在所有测试运行前执行，用于：
 * - 设置全局模拟
 * - 配置测试环境
 * - 清理测试状态
 */

import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';
import '@testing-library/jest-dom';

// vitest 4 + Node 22 下 jsdom 不再暴露 localStorage（Node 实验性全局为 undefined），
// 内存版 polyfill 保证依赖 localStorage 的模块在测试中可用。
function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.get(key) ?? null;
    },
    key(index: number) {
      return [...store.keys()][index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, String(value));
    },
  };
}

if (typeof globalThis.localStorage === 'undefined') {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: createMemoryStorage(),
  });
}
if (typeof globalThis.sessionStorage === 'undefined') {
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: createMemoryStorage(),
  });
}

if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  });
}

// 每个测试后自动清理
afterEach(() => {
  cleanup();
});

// Mock next/font/google (compiler and fonts module import at load time)
vi.mock('next/font/google', () => ({
  Inter: () => ({ variable: '--font-sans', className: 'mock-inter' }),
  JetBrains_Mono: () => ({ variable: '--font-mono', className: 'mock-jbm' }),
}));

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));

// Mock环境变量
process.env.NEXT_PUBLIC_API_BASE_URL = 'http://localhost:8000';
