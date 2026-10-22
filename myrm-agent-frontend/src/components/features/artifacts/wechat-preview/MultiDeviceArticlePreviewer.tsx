/**
 * [INPUT]
 * - wechatPreviewTypes: MultiDeviceArticlePreviewerProps, DeviceViewportMode, WechatThemeId, FontSizeScale
 * - wechatThemes: compileWechatInlineHtml, WECHAT_THEMES
 * - useWechatPreviewStore: useWechatPreviewStore
 *
 * [OUTPUT]
 * - MultiDeviceArticlePreviewer: Interactive multi-device WeChat Official Account previewer component
 *
 * [POS]
 * High-fidelity previewer for WeChat articles across mobile, tablet, and desktop (Item 45 P0).
 * Strictly under 320 lines. Zero `any`.
 */

'use client';

import React, { memo, useMemo, useCallback } from 'react';
import {
  Smartphone,
  Tablet,
  Monitor,
  Copy,
  Check,
  Palette,
  Type,
  Sparkles,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  compileWechatInlineHtml,
  WECHAT_THEMES,
} from './wechatThemes';
import { useWechatPreviewStore } from './useWechatPreviewStore';
import type {
  DeviceViewportMode,
  FontSizeScale,
  MultiDeviceArticlePreviewerProps,
  WechatThemeId,
} from './wechatPreviewTypes';

const THEME_OPTIONS: { id: WechatThemeId; labelKey: string }[] = [
  { id: 'classic', labelKey: 'themeClassic' },
  { id: 'tech', labelKey: 'themeTech' },
  { id: 'enterprise', labelKey: 'themeEnterprise' },
  { id: 'humanist', labelKey: 'themeHumanist' },
];

const SCALE_OPTIONS: { scale: FontSizeScale; labelKey: string }[] = [
  { scale: 'compact', labelKey: 'scaleCompact' },
  { scale: 'normal', labelKey: 'scaleNormal' },
  { scale: 'spacious', labelKey: 'scaleSpacious' },
];

export const MultiDeviceArticlePreviewer: React.FC<MultiDeviceArticlePreviewerProps> = memo(({
  content,
  title = 'WeChat Article',
  filename,
  className = '',
  onCopySuccess,
}) => {
  const t = useTranslations('wechatPreview');

  const {
    viewport,
    themeId,
    scale,
    copied,
    setViewport,
    setThemeId,
    setScale,
    triggerCopiedFeedback,
  } = useWechatPreviewStore();

  const compiledHtml = useMemo(() => {
    return compileWechatInlineHtml(content, themeId, scale);
  }, [content, themeId, scale]);

  const handleCopyWechatHtml = useCallback(async () => {
    try {
      if (typeof window !== 'undefined' && navigator?.clipboard && typeof window.ClipboardItem !== 'undefined') {
        const htmlBlob = new Blob([compiledHtml], { type: 'text/html' });
        const textBlob = new Blob([content], { type: 'text/plain' });
        const item = new window.ClipboardItem({
          'text/html': htmlBlob,
          'text/plain': textBlob,
        });
        await navigator.clipboard.write([item]);
      } else if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(compiledHtml);
      }
      triggerCopiedFeedback();
      if (onCopySuccess) {
        onCopySuccess();
      }
    } catch {
      // Fallback for restricted clipboard contexts
      if (navigator?.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(compiledHtml);
          triggerCopiedFeedback();
          if (onCopySuccess) {
            onCopySuccess();
          }
        } catch {
          // Silent swallow fallback
        }
      }
    }
  }, [compiledHtml, content, triggerCopiedFeedback, onCopySuccess]);

  return (
    <div
      data-testid="wechat-previewer-root"
      className={`flex flex-col h-full w-full bg-slate-100 dark:bg-slate-950 overflow-hidden ${className}`}
    >
      {/* Top HUD Controls */}
      <header
        data-testid="wechat-previewer-toolbar"
        className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 shadow-sm shrink-0 z-10"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="p-1.5 rounded-md bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400">
            <Sparkles className="w-4 h-4" />
          </span>
          <div className="truncate text-xs font-semibold text-slate-800 dark:text-slate-200">
            {filename || title}
          </div>
          <span className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-900/40 rounded">
            {t('badgeLabel')}
          </span>
        </div>

        {/* Viewport Switcher */}
        <div
          data-testid="viewport-switcher"
          className="flex items-center bg-slate-100 dark:bg-slate-800 p-0.5 rounded-lg border border-slate-200/80 dark:border-slate-700/60"
        >
          <button
            type="button"
            data-testid="viewport-mobile"
            onClick={() => {
              setViewport('mobile');
            }}
            title={t('viewportMobile')}
            aria-label={t('viewportMobile')}
            className={`p-1.5 rounded-md transition-all text-xs flex items-center gap-1 ${
              viewport === 'mobile'
                ? 'bg-white dark:bg-slate-700 text-emerald-600 dark:text-emerald-400 shadow-xs font-medium'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            <Smartphone className="w-4 h-4" />
            <span className="hidden md:inline">{t('viewportMobile')}</span>
          </button>
          <button
            type="button"
            data-testid="viewport-tablet"
            onClick={() => {
              setViewport('tablet');
            }}
            title={t('viewportTablet')}
            aria-label={t('viewportTablet')}
            className={`p-1.5 rounded-md transition-all text-xs flex items-center gap-1 ${
              viewport === 'tablet'
                ? 'bg-white dark:bg-slate-700 text-emerald-600 dark:text-emerald-400 shadow-xs font-medium'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            <Tablet className="w-4 h-4" />
            <span className="hidden md:inline">{t('viewportTablet')}</span>
          </button>
          <button
            type="button"
            data-testid="viewport-desktop"
            onClick={() => {
              setViewport('desktop');
            }}
            title={t('viewportDesktop')}
            aria-label={t('viewportDesktop')}
            className={`p-1.5 rounded-md transition-all text-xs flex items-center gap-1 ${
              viewport === 'desktop'
                ? 'bg-white dark:bg-slate-700 text-emerald-600 dark:text-emerald-400 shadow-xs font-medium'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            <Monitor className="w-4 h-4" />
            <span className="hidden md:inline">{t('viewportDesktop')}</span>
          </button>
        </div>

        {/* Theme & Scale Selectors & Copy Button */}
        <div className="flex items-center gap-2">
          {/* Theme Selector */}
          <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-lg border border-slate-200/80 dark:border-slate-700/60">
            <Palette className="w-3.5 h-3.5 text-slate-500" />
            <select
              data-testid="theme-select"
              value={themeId}
              onChange={(e) => {
                setThemeId(e.target.value as WechatThemeId);
              }}
              className="bg-transparent text-xs text-slate-700 dark:text-slate-200 focus:outline-none cursor-pointer"
            >
              {THEME_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id} className="dark:bg-slate-800">
                  {t(opt.labelKey)}
                </option>
              ))}
            </select>
          </div>

          {/* Scale Selector */}
          <div className="hidden sm:flex items-center gap-1 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-lg border border-slate-200/80 dark:border-slate-700/60">
            <Type className="w-3.5 h-3.5 text-slate-500" />
            <select
              data-testid="scale-select"
              value={scale}
              onChange={(e) => {
                setScale(e.target.value as FontSizeScale);
              }}
              className="bg-transparent text-xs text-slate-700 dark:text-slate-200 focus:outline-none cursor-pointer"
            >
              {SCALE_OPTIONS.map((opt) => (
                <option key={opt.scale} value={opt.scale} className="dark:bg-slate-800">
                  {t(opt.labelKey)}
                </option>
              ))}
            </select>
          </div>

          {/* Copy Button */}
          <button
            type="button"
            data-testid="copy-wechat-btn"
            onClick={handleCopyWechatHtml}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg shadow-xs transition-colors ${
              copied
                ? 'bg-emerald-600 text-white'
                : 'bg-emerald-500 hover:bg-emerald-600 text-white'
            }`}
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" />
                <span>{t('copied')}</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>{t('copyWechatHtml')}</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* Main Preview Stage */}
      <main className="flex-1 overflow-auto p-4 sm:p-6 flex justify-center items-start">
        {viewport === 'mobile' && (
          <div
            data-testid="device-frame-mobile"
            className="w-[375px] max-w-full rounded-[36px] border-4 border-slate-800/90 dark:border-slate-700 shadow-2xl bg-white overflow-hidden flex flex-col my-auto transition-all"
          >
            {/* Mobile Top Island Header */}
            <div className="h-6 bg-slate-900 flex justify-center items-center shrink-0">
              <div className="w-20 h-3.5 bg-black rounded-full" />
            </div>

            {/* Mobile Article Content Area */}
            <div className="p-4 sm:p-5 text-slate-900 overflow-y-auto max-h-[720px] select-text">
              <div
                data-testid="wechat-rendered-content"
                dangerouslySetInnerHTML={{ __html: compiledHtml }}
              />
            </div>

            {/* Mobile Bottom Bar Indicator */}
            <div className="h-4 bg-white flex justify-center items-center shrink-0">
              <div className="w-24 h-1 bg-slate-300 rounded-full" />
            </div>
          </div>
        )}

        {viewport === 'tablet' && (
          <div
            data-testid="device-frame-tablet"
            className="w-full max-w-[768px] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xl bg-white p-6 sm:p-8 text-slate-900 transition-all select-text"
          >
            <div
              data-testid="wechat-rendered-content"
              dangerouslySetInnerHTML={{ __html: compiledHtml }}
            />
          </div>
        )}

        {viewport === 'desktop' && (
          <div
            data-testid="device-frame-desktop"
            className="w-full max-w-[680px] rounded-lg border border-slate-200 dark:border-slate-800 shadow-md bg-white p-6 sm:p-8 text-slate-900 transition-all select-text"
          >
            <div
              data-testid="wechat-rendered-content"
              dangerouslySetInnerHTML={{ __html: compiledHtml }}
            />
          </div>
        )}
      </main>
    </div>
  );
});

MultiDeviceArticlePreviewer.displayName = 'MultiDeviceArticlePreviewer';
