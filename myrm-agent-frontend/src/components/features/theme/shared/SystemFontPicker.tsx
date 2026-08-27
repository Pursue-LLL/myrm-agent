/**
 * [INPUT]: @/lib/fonts::FontId, @/lib/utils/classnameUtils::cn
 * [OUTPUT]: SystemFontPicker (POS: 本地系统与自定义字体选择器组件)
 * [POS]: 前端主题设置字体配置子组件，提供 Local Font Access API 枚举、高分开发者预设与自由字体输入。
 */
'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { FONT_CHOICES, POPULAR_SYSTEM_FONTS, type FontId } from '@/lib/fonts';

interface SystemFontPickerProps {
  activeFontId: string;
  onFontChange: (fontId: FontId) => void;
  className?: string;
}

interface FontData {
  family: string;
  fullName?: string;
  postscriptName?: string;
}

export default function SystemFontPicker({ activeFontId, onFontChange, className }: SystemFontPickerProps) {
  const t = useTranslations('settings.fontOptions');
  const [localFonts, setLocalFonts] = useState<string[]>([]);
  const [querying, setQuerying] = useState(false);
  const [supported, setSupported] = useState(false);
  const [customInput, setCustomInput] = useState('');

  useEffect(() => {
    // 探测浏览器是否支持 Local Font Access API
    if (typeof window !== 'undefined' && 'queryLocalFonts' in window) {
      setSupported(true);
    }
  }, []);

  const handleScanLocalFonts = useCallback(async () => {
    if (typeof window === 'undefined' || !('queryLocalFonts' in window)) {
      return;
    }
    setQuerying(true);
    try {
      // @ts-expect-error - queryLocalFonts is a modern Web API
      const availableFonts: FontData[] = await window.queryLocalFonts();
      const families = Array.from(new Set(availableFonts.map((f) => f.family))).sort();
      setLocalFonts(families);
    } catch {
      // 用户拒绝权限或 API 不可用，fallback 使用预设
      setSupported(false);
    } finally {
      setQuerying(false);
    }
  }, []);

  const handleApplyCustomFont = useCallback(() => {
    const trimmed = customInput.trim();
    if (trimmed) {
      onFontChange(trimmed);
      setCustomInput('');
    }
  }, [customInput, onFontChange]);

  const isBuiltin = FONT_CHOICES.some((f) => f.id === activeFontId);
  const isPreset = (POPULAR_SYSTEM_FONTS as readonly string[]).includes(activeFontId);
  const isCustomLocal = !isBuiltin && !isPreset && activeFontId;

  return (
    <div className={cn('space-y-3', className)}>
      {/* 内置预设字体 */}
      <div className="flex flex-wrap gap-2">
        {FONT_CHOICES.map((font) => (
          <button
            key={font.id}
            type="button"
            onClick={() => onFontChange(font.id)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-sm border transition-all',
              activeFontId === font.id
                ? 'border-primary bg-primary/10 text-foreground font-medium shadow-xs'
                : 'border-border bg-secondary/40 text-muted-foreground hover:text-foreground hover:bg-secondary/70',
            )}
          >
            {t(font.id)}
          </button>
        ))}
      </div>

      {/* 常用高分开发者字体预设 */}
      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1.5">{t('popularDeveloperFonts')}</p>
        <div className="flex flex-wrap gap-1.5">
          {POPULAR_SYSTEM_FONTS.map((fontName) => (
            <button
              key={fontName}
              type="button"
              style={{ fontFamily: `"${fontName}", sans-serif` }}
              onClick={() => onFontChange(fontName)}
              className={cn(
                'px-2.5 py-1 rounded-md text-xs border transition-all',
                activeFontId === fontName
                  ? 'border-primary bg-primary/10 text-foreground font-medium shadow-xs'
                  : 'border-border/70 bg-background/50 text-muted-foreground hover:text-foreground hover:border-border',
              )}
            >
              {fontName}
            </button>
          ))}
        </div>
      </div>

      {/* 本地系统字体枚举扫描 (Local Font Access API) */}
      {supported && (
        <div className="pt-1">
          {localFonts.length === 0 ? (
            <button
              type="button"
              disabled={querying}
              onClick={handleScanLocalFonts}
              className="text-xs text-primary hover:underline underline-offset-4 disabled:opacity-50"
            >
              {querying ? t('scanningFonts') : t('scanAllSystemFonts')}
            </button>
          ) : (
            <div className="space-y-1.5">
              <label htmlFor="system-font-select" className="text-xs font-medium text-muted-foreground">
                {t('allInstalledFonts')} ({localFonts.length})
              </label>
              <select
                id="system-font-select"
                value={activeFontId}
                onChange={(e) => onFontChange(e.target.value)}
                className="w-full text-xs rounded-md border border-border bg-background px-2.5 py-1.5 text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
              >
                <option value="" disabled>
                  {t('selectFontPlaceholder')}
                </option>
                {localFonts.map((fontName) => (
                  <option key={fontName} value={fontName} style={{ fontFamily: `"${fontName}", sans-serif` }}>
                    {fontName}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}

      {/* 手动输入任意本地字体名 */}
      <div className="flex items-center gap-2 pt-0.5">
        <input
          type="text"
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleApplyCustomFont();
            }
          }}
          placeholder={t('customFontPlaceholder')}
          className="flex-1 text-xs rounded-md border border-border bg-background px-2.5 py-1.5 text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
        />
        <button
          type="button"
          onClick={handleApplyCustomFont}
          disabled={!customInput.trim()}
          className="px-3 py-1.5 text-xs rounded-md border border-border bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-40 transition-colors"
        >
          {t('apply')}
        </button>
      </div>

      {/* 当前自定义字体指示器 */}
      {isCustomLocal && (
        <div className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded-md bg-primary/5 border border-primary/20">
          <span className="text-muted-foreground">
            {t('activeCustomFont')}:{' '}
            <strong className="text-foreground" style={{ fontFamily: `"${activeFontId}", sans-serif` }}>
              {activeFontId}
            </strong>
          </span>
          <button type="button" onClick={() => onFontChange('inter')} className="text-primary hover:underline">
            {t('resetToDefault')}
          </button>
        </div>
      )}
    </div>
  );
}
