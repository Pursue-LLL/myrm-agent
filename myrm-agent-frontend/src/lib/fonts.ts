/**
 * [INPUT] Theme font ids and platform fallbacks (self-hosted Inter lives in src/app/fonts.ts)
 * [OUTPUT] FONT_STORAGE_KEY, FontId, FONT_CHOICES, getFontStack, ensureFontLoaded.
 * [POS] 全局字体栈 SSOT：theme-engine 写入 --font-override 时使用的字体栈。
 *       AppearancePanel / ThemeProfileProvider 导入 FONT_CHOICES 实现运行时切换；
 *       实际字体文件由 src/app/fonts.ts 通过 next/font/local 自托管。
 */

export const FONT_STORAGE_KEY = 'myrm-font';

export type BuiltinFontId = 'inter' | 'system' | 'atkinson';
export type FontId = BuiltinFontId | (string & {});

interface FontChoice {
  id: FontId;
  stack: string;
}

// 常用本地优质开发者与黑体字体预设候选（用于不支持 queryLocalFonts API 时的快速选用）
export const POPULAR_SYSTEM_FONTS = [
  'JetBrains Mono',
  'Fira Code',
  'Cascadia Code',
  'Source Code Pro',
  'Menlo',
  'Monaco',
  'Consolas',
  'PingFang SC',
  'Microsoft YaHei',
  'Noto Sans SC',
] as const;

// theme-pre-init-script.ts 中有同步副本，修改 stack 时需同步更新
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
  const builtin = FONT_CHOICES.find((f) => f.id === id);
  if (builtin) {
    return builtin.stack;
  }
  // 自定义本地系统字体栈构建：优先使用指定字体名，并追加标准 Fallback 堆栈
  const safeFontName = id.replace(/["\\]/g, '').trim();
  return `"${safeFontName}", var(--font-sans), ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif`;
}

const GOOGLE_FONTS_URL: Partial<Record<string, string>> = {
  atkinson: 'https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;500;600;700&display=swap',
};

const loadedFonts = new Set<string>();

export function ensureFontLoaded(id: FontId): void {
  if (loadedFonts.has(id) || typeof document === 'undefined') {
    return;
  }
  const url = GOOGLE_FONTS_URL[id];
  if (!url) {
    return;
  }
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = url;
  document.head.appendChild(link);
  loadedFonts.add(id);
}
