/**
 * [INPUT] System & Web font fallbacks (Turbopack standalone / local font tokens)
 * [OUTPUT] fontSans, fontMono: CSS variable declarations for standard typography.
 * [OUTPUT] FONT_STORAGE_KEY, FontId, FONT_CHOICES, getFontStack, ensureFontLoaded.
 * [POS] 全局字体系统 SSOT。layout.tsx 导入实例用于 self-host 加载；
 *       AppearancePanel / ThemeProfileProvider 导入 FONT_CHOICES 实现运行时切换。
 */

export const fontSans = {
  variable: '--font-sans',
  className: 'font-sans',
};

export const fontMono = {
  variable: '--font-mono',
  className: 'font-mono',
};

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
