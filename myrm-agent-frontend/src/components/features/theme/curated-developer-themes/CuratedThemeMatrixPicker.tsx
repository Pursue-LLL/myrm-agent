/**
 * [INPUT]
 * - ./curatedThemeTypes::CuratedThemeId, CuratedThemePreset
 * - ./curatedThemePresets::CURATED_DEVELOPER_THEMES, getCuratedThemeById
 * - ./useCuratedThemeStore::useCuratedThemeStore
 * - lucide-react::Palette, Check, Sparkles, Terminal, RotateCcw, ShieldCheck
 *
 * [OUTPUT]
 * - CuratedThemeMatrixPicker: 精选开发者高对比度暗色主题矩阵可视化调色向导组件
 *
 * [POS]
 * 在系统设置-外观及全局调色向导中提供工业级经典开发者高对比度暗色主题矩阵选择器。
 */

'use client';

import React, { useCallback, useMemo } from 'react';
import { Palette, Check, Sparkles, Terminal, RotateCcw, ShieldCheck } from 'lucide-react';
import type { CuratedThemeId, CuratedThemePreset } from './curatedThemeTypes';
import { CURATED_DEVELOPER_THEMES, getCuratedThemeById } from './curatedThemePresets';
import { useCuratedThemeStore } from './useCuratedThemeStore';

export interface CuratedThemeMatrixPickerProps {
  onThemeSelect?: (themeId: CuratedThemeId) => void;
  className?: string;
}

export const CuratedThemeMatrixPicker: React.FC<CuratedThemeMatrixPickerProps> = ({
  onThemeSelect,
  className = '',
}) => {
  const activeThemeId = useCuratedThemeStore((s) => s.activeThemeId);
  const setTheme = useCuratedThemeStore((s) => s.setTheme);
  const resetToDefault = useCuratedThemeStore((s) => s.resetToDefault);
  const syncWithSystemDark = useCuratedThemeStore((s) => s.syncWithSystemDark);
  const setSyncWithSystemDark = useCuratedThemeStore((s) => s.setSyncWithSystemDark);

  const activePreset = useMemo(() => {
    return getCuratedThemeById(activeThemeId) ?? null;
  }, [activeThemeId]);

  const handleSelectTheme = useCallback(
    (id: CuratedThemeId) => {
      setTheme(id);
      if (onThemeSelect) {
        onThemeSelect(id);
      }
    },
    [setTheme, onThemeSelect]
  );

  return (
    <section
      aria-label="精选开发者暗色主题矩阵选择器"
      className={`flex flex-col gap-4 rounded-xl border border-border/80 bg-card/60 p-4 text-xs text-card-foreground shadow-xs backdrop-blur-xs ${className}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-border/60">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Palette className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
              <span>经典开发者暗色主题矩阵</span>
              <span className="px-1.5 py-0.2 rounded-full bg-primary/15 text-primary text-[10px] font-mono font-medium">
                PRO
              </span>
            </h3>
            <p className="text-[11px] text-muted-foreground">
              精选 6 款工业级终端与编辑器高对比度经典配色 · 零重绘卡顿
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground hover:text-foreground transition-colors">
            <input
              type="checkbox"
              checked={syncWithSystemDark}
              onChange={(e) => {
                setSyncWithSystemDark(e.target.checked);
              }}
              className="rounded border-border text-primary focus:ring-primary h-3.5 w-3.5"
            />
            <span className="text-[11px]">跟随系统深色</span>
          </label>
          <button
            type="button"
            onClick={resetToDefault}
            className="flex items-center gap-1 px-2 py-1 rounded text-[11px] text-muted-foreground hover:bg-muted transition-colors"
            aria-label="恢复默认暗色模式"
          >
            <RotateCcw className="w-3 h-3" aria-hidden="true" />
            <span>默认</span>
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
        {CURATED_DEVELOPER_THEMES.map((theme: CuratedThemePreset) => {
          const isSelected = activeThemeId === theme.id;
          return (
            <button
              key={theme.id}
              type="button"
              onClick={() => {
                handleSelectTheme(theme.id);
              }}
              className={`group flex flex-col justify-between p-3 rounded-lg border text-left transition-all ${
                isSelected
                  ? 'border-primary bg-primary/5 ring-1 ring-primary shadow-xs'
                  : 'border-border/70 bg-background/50 hover:border-primary/50 hover:bg-background/80'
              }`}
              aria-pressed={isSelected}
              aria-label={`选择 ${theme.name} 主题`}
            >
              <div className="flex items-start justify-between gap-1.5 mb-2 w-full">
                <div className="truncate">
                  <div className="flex items-center gap-1.5 font-semibold text-foreground text-xs">
                    <span>{theme.name}</span>
                    {isSelected && (
                      <Check className="w-3.5 h-3.5 text-primary shrink-0" aria-hidden="true" />
                    )}
                  </div>
                  <p className="text-[10px] text-muted-foreground truncate mt-0.5" title={theme.tagline}>
                    {theme.tagline}
                  </p>
                </div>

                <span className="flex items-center gap-0.5 px-1.5 py-0.2 rounded bg-muted text-[10px] font-mono text-muted-foreground shrink-0 border border-border/40">
                  <ShieldCheck className="w-2.5 h-2.5 text-emerald-500" aria-hidden="true" />
                  <span>{theme.contrastRatio.split(' ')[0]}</span>
                </span>
              </div>

              <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-border/40 w-full">
                {theme.previewPalette.map((color, idx) => (
                  <span
                    key={`${theme.id}-${idx}-${color}`}
                    className="w-4 h-4 rounded-full border border-black/20 shadow-xs shrink-0"
                    style={{ backgroundColor: color }}
                    title={color}
                  />
                ))}
              </div>
            </button>
          );
        })}
      </div>

      <div className="rounded-lg border border-border/80 bg-background/90 p-3 mt-1 font-mono text-[11px]">
        <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/40 text-muted-foreground text-[10px]">
          <span className="flex items-center gap-1.5">
            <Terminal className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
            <span>实时代码与 ANSI 终端色调预览</span>
          </span>
          <span className="text-primary font-medium">
            {activePreset ? activePreset.name : '系统默认暗色'}
          </span>
        </div>

        <div
          className="p-3 rounded-md border transition-colors leading-relaxed"
          style={{
            backgroundColor: activePreset ? activePreset.tokens.background : '#18181b',
            borderColor: activePreset ? activePreset.tokens.border : '#27272a',
            color: activePreset ? activePreset.tokens.foreground : '#f4f4f5',
          }}
        >
          <div className="flex items-center gap-2">
            <span style={{ color: activePreset ? activePreset.tokens.accent : '#c084fc' }}>
              import
            </span>
            <span>&#123; createAgent &#125;</span>
            <span style={{ color: activePreset ? activePreset.tokens.accent : '#c084fc' }}>
              from
            </span>
            <span style={{ color: activePreset ? activePreset.ansi.green : '#4ade80' }}>
              &apos;@myrm/agent-core&apos;;
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span style={{ color: activePreset ? activePreset.tokens.primary : '#38bdf8' }}>
              const
            </span>
            <span>runner =</span>
            <span style={{ color: activePreset ? activePreset.tokens.accent : '#c084fc' }}>
              createAgent
            </span>
            <span>(&#123;</span>
            <span style={{ color: activePreset ? activePreset.ansi.yellow : '#facc15' }}>
              theme:
            </span>
            <span style={{ color: activePreset ? activePreset.ansi.green : '#4ade80' }}>
              &apos;{activeThemeId}&apos;
            </span>
            <span>&#125;);</span>
          </div>
        </div>
      </div>
    </section>
  );
};
