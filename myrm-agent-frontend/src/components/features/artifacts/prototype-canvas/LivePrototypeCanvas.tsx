/**
 * [INPUT]
 * - prototypeCanvasTypes: LivePrototypeCanvasProps, PrototypeViewport
 * - usePrototypeCanvasStore: usePrototypeCanvasStore
 * - LivePrototypeSandbox: LivePrototypeSandbox
 * - PrototypeAnnotationOverlay: PrototypeAnnotationOverlay
 *
 * [OUTPUT]
 * - LivePrototypeCanvas: Interactive prototype canvas with HUD toolbar and spec handoff
 *
 * [POS]
 * Primary canvas controller for Intent-to-Interactive-Prototype workflow (Item 46 P0).
 * Strictly under 320 lines. Zero `any`.
 */

'use client';

import React, { memo, useState, useCallback } from 'react';
import {
  Monitor,
  Tablet,
  Smartphone,
  Sparkles,
  MousePointerClick,
  FileCode,
  Check,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { usePrototypeCanvasStore } from './usePrototypeCanvasStore';
import { LivePrototypeSandbox } from './LivePrototypeSandbox';
import { PrototypeAnnotationOverlay } from './PrototypeAnnotationOverlay';
import type { LivePrototypeCanvasProps } from './prototypeCanvasTypes';

export const LivePrototypeCanvas: React.FC<LivePrototypeCanvasProps> = memo(({
  content,
  title = 'Interactive Prototype',
  filename,
  className = '',
  onHandoffSpec,
}) => {
  const t = useTranslations('prototypeCanvas');

  const {
    viewport,
    isAnnotating,
    setViewport,
    setAnnotating,
    generateHandoffSpec,
    annotations,
  } = usePrototypeCanvasStore();

  const [pendingElement, setPendingElement] = useState<{
    tag: string;
    selector: string;
    position?: { x: number; y: number };
  } | null>(null);

  const [handoffSuccess, setHandoffSuccess] = useState(false);

  const handleElementSelect = useCallback((el: {
    tag: string;
    selector: string;
    rect: { x: number; y: number; width: number; height: number };
  }) => {
    setPendingElement({
      tag: el.tag,
      selector: el.selector,
      position: { x: el.rect.x, y: el.rect.y },
    });
  }, []);

  const handleClearPending = useCallback(() => {
    setPendingElement(null);
  }, []);

  const handleHandoff = useCallback(() => {
    const payload = generateHandoffSpec(filename || title, content);
    setHandoffSuccess(true);
    if (onHandoffSpec) {
      onHandoffSpec(payload);
    }
    setTimeout(() => {
      setHandoffSuccess(false);
    }, 3000);
  }, [filename, title, content, generateHandoffSpec, onHandoffSpec]);

  const unresolvedCount = annotations.filter((a) => !a.resolved).length;

  return (
    <div
      data-testid="live-prototype-canvas-root"
      className={`relative flex flex-col h-full w-full bg-slate-100 dark:bg-slate-950 overflow-hidden ${className}`}
    >
      {/* Top HUD Toolbar */}
      <header
        data-testid="prototype-canvas-toolbar"
        className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 shadow-sm shrink-0 z-10"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="p-1.5 rounded-md bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400">
            <Sparkles className="w-4 h-4" />
          </span>
          <div className="truncate text-xs font-semibold text-slate-800 dark:text-slate-200">
            {filename || title}
          </div>
          <span className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-medium text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/40 rounded">
            {t('badgeLabel')}
          </span>
        </div>

        {/* Viewport Switcher */}
        <div
          data-testid="prototype-viewport-switcher"
          className="flex items-center bg-slate-100 dark:bg-slate-800 p-0.5 rounded-lg border border-slate-200/80 dark:border-slate-700/60"
        >
          <button
            type="button"
            data-testid="viewport-desktop-btn"
            onClick={() => {
              setViewport('desktop');
            }}
            title={t('viewportDesktop')}
            aria-label={t('viewportDesktop')}
            className={`p-1.5 rounded-md transition-all text-xs flex items-center gap-1 ${
              viewport === 'desktop'
                ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-xs font-medium'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            <Monitor className="w-4 h-4" />
            <span className="hidden md:inline">{t('viewportDesktop')}</span>
          </button>
          <button
            type="button"
            data-testid="viewport-tablet-btn"
            onClick={() => {
              setViewport('tablet');
            }}
            title={t('viewportTablet')}
            aria-label={t('viewportTablet')}
            className={`p-1.5 rounded-md transition-all text-xs flex items-center gap-1 ${
              viewport === 'tablet'
                ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-xs font-medium'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            <Tablet className="w-4 h-4" />
            <span className="hidden md:inline">{t('viewportTablet')}</span>
          </button>
          <button
            type="button"
            data-testid="viewport-mobile-btn"
            onClick={() => {
              setViewport('mobile');
            }}
            title={t('viewportMobile')}
            aria-label={t('viewportMobile')}
            className={`p-1.5 rounded-md transition-all text-xs flex items-center gap-1 ${
              viewport === 'mobile'
                ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-xs font-medium'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            <Smartphone className="w-4 h-4" />
            <span className="hidden md:inline">{t('viewportMobile')}</span>
          </button>
        </div>

        {/* Action Controls: Annotation Mode & Spec Handoff */}
        <div className="flex items-center gap-2">
          {/* Toggle Annotation Mode */}
          <button
            type="button"
            data-testid="toggle-annotating-btn"
            onClick={() => {
              setAnnotating(!isAnnotating);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-all ${
              isAnnotating
                ? 'bg-amber-500 text-slate-900 border-amber-600 shadow-xs'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            <MousePointerClick className="w-3.5 h-3.5" />
            <span>{isAnnotating ? t('annotatingActive') : t('clickToAnnotate')}</span>
            {unresolvedCount > 0 && (
              <span className="px-1 py-0.2 bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 text-[10px] rounded-full">
                {unresolvedCount}
              </span>
            )}
          </button>

          {/* Approve & Handoff Spec */}
          <button
            type="button"
            data-testid="handoff-spec-btn"
            onClick={handleHandoff}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg text-white shadow-xs transition-colors ${
              handoffSuccess
                ? 'bg-emerald-600'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {handoffSuccess ? (
              <>
                <Check className="w-3.5 h-3.5" />
                <span>{t('specHandoffDone')}</span>
              </>
            ) : (
              <>
                <FileCode className="w-3.5 h-3.5" />
                <span>{t('approveAndHandoffSpec')}</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* Main Sandbox Stage with Overlay */}
      <main className="relative flex-1 overflow-hidden">
        <LivePrototypeSandbox
          content={content}
          viewport={viewport}
          isAnnotating={isAnnotating}
          onElementSelect={handleElementSelect}
        />

        <PrototypeAnnotationOverlay
          pendingElement={pendingElement}
          onClearPending={handleClearPending}
        />
      </main>
    </div>
  );
});

LivePrototypeCanvas.displayName = 'LivePrototypeCanvas';
