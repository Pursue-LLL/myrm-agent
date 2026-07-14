/**
 * [INPUT] '@/lib/fonts'::FONT_CHOICES, FONT_STORAGE_KEY, FontId, getFontStack, ensureFontLoaded (POS: 全局字体系统 SSOT)
 * [INPUT] 'next-intl'::useTranslations (POS: i18n 翻译)
 * [INPUT] '@/lib/utils/classnameUtils'::cn (POS: 样式合并工具)
 * [OUTPUT] FontPicker: 字体选择器组件，支持 3 种预设字体方案。
 * [POS] 设置页外观子组件。通过 CSS 变量 --font-override 切换全局正文字体，持久化到 localStorage。
 *       设计模式与 SkinPicker 一致：data-attribute + localStorage + CSS 变量。
 */
'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { FONT_CHOICES, FONT_STORAGE_KEY, type FontId, getFontStack, ensureFontLoaded } from '@/lib/fonts';

function applyFont(fontId: FontId) {
  const el = document.documentElement;
  if (fontId === 'inter') {
    el.style.removeProperty('--font-override');
    el.removeAttribute('data-font');
  } else {
    el.style.setProperty('--font-override', getFontStack(fontId));
    el.setAttribute('data-font', fontId);
  }
}

function getStoredFont(): FontId {
  if (typeof window === 'undefined') return 'inter';
  return (localStorage.getItem(FONT_STORAGE_KEY) as FontId) || 'inter';
}

const FONT_PREVIEW_FAMILY: Record<FontId, string> = {
  inter: 'Inter, sans-serif',
  system: 'ui-sans-serif, -apple-system, sans-serif',
  atkinson: '"Atkinson Hyperlegible Next", sans-serif',
};

const FontPicker = ({ className }: { className?: string }) => {
  const t = useTranslations('settings.fontOptions');
  const [mounted, setMounted] = useState(false);
  const [activeFont, setActiveFont] = useState<FontId>('inter');

  useEffect(() => {
    const stored = getStoredFont();
    setActiveFont(stored);
    if (stored !== 'inter') {
      ensureFontLoaded(stored);
      applyFont(stored);
    }
    setMounted(true);
  }, []);

  const handleSelect = useCallback((fontId: FontId) => {
    setActiveFont(fontId);
    ensureFontLoaded(fontId);
    applyFont(fontId);
    localStorage.setItem(FONT_STORAGE_KEY, fontId);
  }, []);

  if (!mounted) return null;

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {FONT_CHOICES.map((font) => (
        <button
          key={font.id}
          onClick={() => handleSelect(font.id)}
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all border',
            activeFont === font.id
              ? 'border-primary bg-primary/10 text-foreground ring-1 ring-accent-warm/35 shadow-brand'
              : 'border-border bg-secondary/40 text-muted-foreground hover:bg-secondary hover:text-foreground',
          )}
        >
          <span
            className="w-6 text-center text-base leading-none shrink-0"
            style={{ fontFamily: FONT_PREVIEW_FAMILY[font.id] }}
            aria-hidden
          >
            Aa
          </span>
          {t(font.id)}
        </button>
      ))}
    </div>
  );
};

export default FontPicker;
