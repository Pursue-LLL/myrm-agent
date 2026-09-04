/**
 * Vitest测试环境配置
 *
 * 这个文件在所有测试运行前执行，用于：
 * - 设置全局模拟
 * - 配置测试环境
 * - 清理测试状态
 */

import { JSDOM } from 'jsdom';

if (typeof document === 'undefined') {
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  // @ts-expect-error polyfill for non-browser testing
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.navigator = dom.window.navigator;
}

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

// jsdom 未实现 Pointer Capture API，Radix Select 依赖它做指针事件处理。
// 提供空实现以让基于 Radix 的 Select 交互（测试中点击 trigger/option）正常工作。
if (typeof Element !== 'undefined' && typeof Element.prototype.hasPointerCapture !== 'function') {
  Object.defineProperty(Element.prototype, 'hasPointerCapture', {
    configurable: true,
    value: () => false,
  });
  Object.defineProperty(Element.prototype, 'setPointerCapture', {
    configurable: true,
    value: () => {},
  });
  Object.defineProperty(Element.prototype, 'releasePointerCapture', {
    configurable: true,
    value: () => {},
  });
}

// 每个测试后自动清理
afterEach(() => {
  cleanup();
  try {
    vi.clearAllTimers();
  } catch {
    // ignore in environments where fake timers were not activated
  }
});

// Mock next/font/google (compiler and fonts module import at load time)
vi.mock('next/font/google', () => ({
  Inter: () => ({ variable: '--font-sans', className: 'mock-inter' }),
  JetBrains_Mono: () => ({ variable: '--font-mono', className: 'mock-jbm' }),
}));

// ===== next-intl Mock 强制规范（全员必须遵守，违反会导致 Vitest OOM） =====
// 根因：useTranslations() 若每次调用都返回一个新函数引用，
// 依赖它的 useCallback/useEffect（dep 数组含 t）会在每次渲染时重建 → 组件无限重渲染 → 堆溢出 OOM。
//
// 规则：
// 1. 本文件提供全局兜底：useTranslations 返回模块级单例 stableT（identity 实现，t(key)=key）。
//    不覆盖 next-intl mock 的测试文件自动获得稳定引用。
// 2. 测试文件需要自定义翻译时，【禁止】写成：
//      vi.mock('next-intl', () => ({ useTranslations: () => (key) => key }))
//    （每次调用创建新函数 = 不稳定引用）
//    必须先将逻辑提取为模块级 const，再在 mock 中返回该引用：
//      const stableT = (key: string) => key;
//      vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
// 3. 自带的参数插值逻辑同样必须放进 stableT（参见测试文件中的自定义 stableT 模式）。
export const stableT: (key: string) => string = (key) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
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
