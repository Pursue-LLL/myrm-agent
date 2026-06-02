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

// 每个测试后自动清理
afterEach(() => {
  cleanup();
});

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
