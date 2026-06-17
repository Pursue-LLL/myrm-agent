/**
 * [INPUT] 'next/font/google'::Inter, JetBrains_Mono (POS: Next.js self-hosted Google Fonts)
 * [OUTPUT] fontSans, fontMono: next/font instances (Inter / JetBrains Mono).
 * [OUTPUT] FONT_STORAGE_KEY, FontId, FONT_CHOICES, getFontStack, ensureFontLoaded.
 * [POS] 全局字体系统 SSOT。layout.tsx 导入实例用于 self-host 加载；
 *       FontPicker / ThemeProvider 导入 FONT_CHOICES 实现运行时切换。
 */
import { Inter, JetBrains_Mono } from 'next/font/google';

export const fontSans = Inter({
  subsets: ['latin', 'latin-ext'],
  variable: '--font-sans',
  display: 'swap',
  fallback: [
    'ui-sans-serif',
    '-apple-system',
    'BlinkMacSystemFont',
    'Segoe UI',
    'PingFang SC',
    'Noto Sans SC',
    'Microsoft YaHei',
    'sans-serif',
  ],
});

export const fontMono = JetBrains_Mono({
  subsets: ['latin', 'latin-ext'],
  variable: '--font-mono',
  display: 'swap',
  fallback: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
});

export const FONT_STORAGE_KEY = 'myrm-font';

export type FontId = 'inter' | 'system' | 'atkinson';

interface FontChoice {
  id: FontId;
  stack: string;
}

// layout.tsx blocking script 中有同步副本，修改 stack 时需同步更新
export const FONT_CHOICES: FontChoice[] = [
  {
    id: 'inter',
    stack: `var(--font-sans), ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif`,
  },
  {
    id: 'system',
    stack: `ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif`,
  },
  {
    id: 'atkinson',
    stack: `"Atkinson Hyperlegible Next", ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif`,
  },
];

export function getFontStack(id: FontId): string {
  return FONT_CHOICES.find((f) => f.id === id)?.stack ?? FONT_CHOICES[0].stack;
}

const GOOGLE_FONTS_URL: Partial<Record<FontId, string>> = {
  atkinson:
    'https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;500;600;700&display=swap',
};

const loadedFonts = new Set<FontId>();

export function ensureFontLoaded(id: FontId): void {
  if (loadedFonts.has(id) || typeof document === 'undefined') return;
  const url = GOOGLE_FONTS_URL[id];
  if (!url) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = url;
  document.head.appendChild(link);
  loadedFonts.add(id);
}
