/**
 * [INPUT]
 * @/hooks/ui/useDesktopVibrancy::useDesktopVibrancy, VibrancyStyleType (POS: Desktop vibrancy hook)
 * next-intl::useTranslations (POS: Internationalization hook)
 *
 * [OUTPUT]
 * - LiquidVibrancyStatusHub: HUD floating pill and tuner panel for desktop acrylic & liquid vibrancy
 *
 * [POS]
 * Desktop Liquid Vibrancy HUD & Tuner Component (Item 17).
 * Single file < 260 lines. Zero `any` types.
 */

'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  useDesktopVibrancy,
  type VibrancyStyleType,
} from '@/hooks/ui/useDesktopVibrancy';

export const LiquidVibrancyStatusHub: React.FC = () => {
  const t = useTranslations('vibrancy');
  const {
    platform,
    supportedStyles,
    currentStyle,
    isBlurActive,
    blurIntensity,
    isTauri,
    setStyle,
    setBlurIntensity,
    toggleVibrancy,
  } = useDesktopVibrancy();

  const [isOpen, setIsOpen] = useState<boolean>(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Close popover on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const styleLabels: Record<VibrancyStyleType, string> = {
    mica: t('styleMica'),
    acrylic: t('styleAcrylic'),
    vibrant_dark: t('styleVibrantDark'),
    ultra_thin: t('styleUltraThin'),
    disabled: t('styleDisabled'),
  };

  return (
    <div className="fixed bottom-6 left-6 z-40 select-none" ref={popoverRef}>
      {/* Floating HUD Pill */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-label={t('triggerAriaLabel')}
        title={t('triggerTooltip')}
        className={`glass-floating-bar flex items-center gap-2.5 px-3 py-1.5 rounded-full text-slate-100 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500/50 ${
          isBlurActive ? 'border-blue-400/40 animate-liquid-glow' : 'opacity-60 hover:opacity-100'
        }`}
      >
        <div
          className={`w-2.5 h-2.5 rounded-full transition-all ${
            isBlurActive
              ? 'bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.8)] animate-pulse'
              : 'bg-slate-500'
          }`}
        />
        <span className="text-xs font-semibold tracking-wide flex items-center gap-1.5">
          <span>{isBlurActive ? styleLabels[currentStyle] : t('statusDisabled')}</span>
        </span>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-slate-300 hidden sm:inline">
          ⌥⌘V
        </span>
      </button>

      {/* Floating Tuner Popover */}
      {isOpen && (
        <div className="glass-panel absolute bottom-12 left-0 w-80 rounded-2xl p-5 shadow-2xl border border-white/15 animate-in fade-in slide-in-from-bottom-2 duration-200">
          {/* Header */}
          <div className="flex items-center justify-between pb-3 border-b border-white/10">
            <div>
              <h4 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                <span>{t('panelTitle')}</span>
                <span className="px-1.5 py-0.5 text-[9px] font-mono font-bold rounded bg-blue-500/20 text-blue-300 border border-blue-400/30">
                  {isTauri ? 'TAURI NATIVE' : 'WEB CSS'}
                </span>
              </h4>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {t('platformTag', { platform: platform.toUpperCase() })}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-label={t('quickToggleAriaLabel')}
              aria-checked={isBlurActive}
              onClick={toggleVibrancy}
              className={`w-10 h-5.5 rounded-full transition-colors relative focus:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                isBlurActive ? 'bg-blue-600' : 'bg-slate-700'
              }`}
            >
              <span
                className={`block w-3.5 h-3.5 rounded-full bg-white transition-transform ${
                  isBlurActive ? 'translate-x-5' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          {/* Style Selector Grid */}
          <div className="py-4">
            <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-300 mb-2">
              {t('styleLabel')}
            </label>
            <div className="grid grid-cols-2 gap-2">
              {supportedStyles.map((styleKey) => {
                const isSelected = currentStyle === styleKey;
                return (
                  <button
                    key={styleKey}
                    type="button"
                    onClick={() => setStyle(styleKey)}
                    className={`px-3 py-2 rounded-xl text-left text-xs font-medium transition-all border ${
                      isSelected
                        ? 'border-blue-400 bg-blue-500/20 text-white ring-1 ring-blue-400/40'
                        : 'border-white/5 bg-white/5 text-slate-300 hover:bg-white/10 hover:border-white/10'
                    }`}
                  >
                    <span className="block truncate">{styleLabels[styleKey]}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Blur Intensity Slider */}
          {isBlurActive && (
            <div className="pt-1 pb-3">
              <div className="flex justify-between items-center mb-1.5">
                <label htmlFor="blur-intensity-slider" className="text-[11px] font-semibold uppercase tracking-wider text-slate-300">
                  {t('intensityLabel')}
                </label>
                <span className="text-xs font-mono font-bold text-blue-400">
                  {blurIntensity}%
                </span>
              </div>
              <input
                id="blur-intensity-slider"
                type="range"
                min={10}
                max={100}
                value={blurIntensity}
                onChange={(e) => setBlurIntensity(Number(e.target.value))}
                className="w-full accent-blue-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
              />
            </div>
          )}

          {/* Platform Capabilities Note */}
          <div className="pt-3 border-t border-white/10 flex items-start gap-2 text-[10px] text-slate-400 leading-relaxed">
            <svg className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{t('platformHint')}</span>
          </div>
        </div>
      )}
    </div>
  );
};
