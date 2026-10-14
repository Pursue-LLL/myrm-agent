'use client';

import React, { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Code, Compass, Cpu, Flame, Lock, Minimize2, RotateCcw, SlidersHorizontal, Unlock, X } from 'lucide-react';

export interface RadarDimensionValues {
  recency: number;
  actionability: number;
  technical_depth: number;
  conciseness: number;
  breadth: number;
}

type RadarPresetKey = 'balanced' | 'code' | 'research';

export interface DynamicPreferenceRadarDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  values: RadarDimensionValues;
  locked: boolean;
  onValueChange: (dimension: keyof RadarDimensionValues, value: number) => void;
  onToggleLock: (nextLocked: boolean) => void;
  onReset: () => void;
  onSelectPreset?: (preset: RadarPresetKey) => void;
  className?: string;
}

export const RADAR_PRESETS: Record<RadarPresetKey, { values: RadarDimensionValues }> = {
  balanced: {
    values: { recency: 1.0, actionability: 1.0, technical_depth: 1.0, conciseness: 1.0, breadth: 1.0 },
  },
  code: {
    values: { recency: 1.5, actionability: 2.5, technical_depth: 2.0, conciseness: 1.8, breadth: 0.5 },
  },
  research: {
    values: { recency: 2.0, actionability: 0.5, technical_depth: 2.5, conciseness: 0.8, breadth: 2.5 },
  },
};

const PRESET_LABEL_KEYS = {
  balanced: 'presetBalanced',
  code: 'presetCode',
  research: 'presetResearch',
} as const satisfies Record<RadarPresetKey, string>;

const DIMENSIONS = [
  { key: 'recency', labelKey: 'dimensionRecency', hintKey: 'dimensionRecencyHint', icon: Flame },
  { key: 'actionability', labelKey: 'dimensionActionability', hintKey: 'dimensionActionabilityHint', icon: Code },
  { key: 'technical_depth', labelKey: 'dimensionDepth', hintKey: 'dimensionDepthHint', icon: Cpu },
  { key: 'conciseness', labelKey: 'dimensionConciseness', hintKey: 'dimensionConcisenessHint', icon: Minimize2 },
  { key: 'breadth', labelKey: 'dimensionBreadth', hintKey: 'dimensionBreadthHint', icon: Compass },
] as const satisfies ReadonlyArray<{
  key: keyof RadarDimensionValues;
  labelKey: string;
  hintKey: string;
  icon: React.ComponentType<{ className?: string }>;
}>;

const SVG_SIZE = 240;
const CENTER = SVG_SIZE / 2;
const MAX_RADIUS = 90;
const MIN_BOUND = 0.05;
const MAX_BOUND = 3.0;

export const DynamicPreferenceRadarDrawer: React.FC<DynamicPreferenceRadarDrawerProps> = ({
  isOpen,
  onClose,
  values,
  locked,
  onValueChange,
  onToggleLock,
  onReset,
  onSelectPreset,
  className = '',
}) => {
  const t = useTranslations('chat.preferenceRadar');
  const commonT = useTranslations('common');
  const radarPoints = useMemo(() => {
    const total = DIMENSIONS.length;
    return DIMENSIONS.map((dim, index) => {
      const angle = -Math.PI / 2 + (index * 2 * Math.PI) / total;
      const rawVal = values[dim.key] ?? 1.0;
      const normalized = Math.max(MIN_BOUND, Math.min(MAX_BOUND, rawVal)) / MAX_BOUND;
      const r = normalized * MAX_RADIUS;
      const x = CENTER + r * Math.cos(angle);
      const y = CENTER + r * Math.sin(angle);
      return { x, y, angle };
    });
  }, [values]);

  const gridPolygons = useMemo(() => {
    const total = DIMENSIONS.length;
    return [0.33, 0.66, 1.0].map((ratio) => {
      const pts = DIMENSIONS.map((_, index) => {
        const angle = -Math.PI / 2 + (index * 2 * Math.PI) / total;
        const r = ratio * MAX_RADIUS;
        return `${(CENTER + r * Math.cos(angle)).toFixed(1)},${(CENTER + r * Math.sin(angle)).toFixed(1)}`;
      });
      return pts.join(' ');
    });
  }, []);

  const semanticSummary = useMemo(() => {
    const entries = DIMENSIONS.map((d) => ({
      key: d.key,
      label: t(d.labelKey),
      val: values[d.key] ?? 1.0,
    })).sort((a, b) => b.val - a.val);

    const highest = entries[0];
    const second = entries[1];

    if (highest.val < 1.15 && entries[entries.length - 1].val > 0.85) {
      return t('summaryBalanced');
    }
    return t('summaryFocused', {
      first: highest.label,
      firstValue: highest.val.toFixed(1),
      second: second.label,
      secondValue: second.val.toFixed(1),
    });
  }, [values, t]);

  if (!isOpen) {
    return null;
  }

  return (
    <aside
      data-testid="preference-radar-drawer"
      className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col border-l border-border bg-background/95 p-5 shadow-2xl backdrop-blur-md transition-all duration-300 dark:bg-zinc-950/95 sm:max-w-md ${className}`}
      aria-label={t('ariaLabel')}
    >
      {/* 顶部标题与操作栏 */}
      <div className="flex items-center justify-between border-b border-border/60 pb-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <SlidersHorizontal className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-foreground">{t('title')}</h2>
            <p className="text-xs text-muted-foreground">{t('subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            data-testid="radar-toggle-lock"
            onClick={() => onToggleLock(!locked)}
            className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
              locked
                ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
                : 'bg-muted text-muted-foreground hover:text-foreground'
            }`}
            title={locked ? t('lockedTitle') : t('unlockedTitle')}
          >
            {locked ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
            <span>{locked ? t('lockedLabel') : t('adaptiveLabel')}</span>
          </button>
          <button
            type="button"
            data-testid="radar-close-button"
            onClick={onClose}
            aria-label={commonT('close')}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* 语义摘要与一键预设栏 */}
      <div className="my-3 space-y-2">
        <div className="rounded-lg border border-border/50 bg-primary/5 px-3 py-2 text-xs text-primary/90 font-medium">
          {semanticSummary}
        </div>
        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
          {(Object.keys(RADAR_PRESETS) as RadarPresetKey[]).map((presetKey) => {
            const preset = RADAR_PRESETS[presetKey];
            return (
              <button
                key={presetKey}
                type="button"
                data-testid={`preset-${presetKey}`}
                disabled={locked}
                onClick={() => {
                  if (onSelectPreset) {
                    onSelectPreset(presetKey);
                  } else {
                    (Object.keys(preset.values) as Array<keyof RadarDimensionValues>).forEach((k) => {
                      onValueChange(k, preset.values[k]);
                    });
                  }
                }}
                className="whitespace-nowrap rounded-md border border-border/70 bg-muted/40 px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-primary/10 hover:text-primary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {t(PRESET_LABEL_KEYS[presetKey])}
              </button>
            );
          })}
        </div>
      </div>

      {/* 中部雷达矢量图展示区 */}
      <div className="flex flex-col items-center justify-center py-4">
        <div className="relative flex items-center justify-center">
          <svg width={SVG_SIZE} height={SVG_SIZE} className="overflow-visible">
            {/* 背景同心参考网格 */}
            {gridPolygons.map((points, idx) => (
              <polygon
                key={`grid-${idx}`}
                points={points}
                fill="none"
                stroke="currentColor"
                strokeDasharray={idx === 0 ? '2,2' : undefined}
                className="text-border/60"
                strokeWidth={1}
              />
            ))}

            {/* 径向轴线 */}
            {DIMENSIONS.map((_, index) => {
              const angle = -Math.PI / 2 + (index * 2 * Math.PI) / DIMENSIONS.length;
              const x2 = CENTER + MAX_RADIUS * Math.cos(angle);
              const y2 = CENTER + MAX_RADIUS * Math.sin(angle);
              return (
                <line
                  key={`axis-${index}`}
                  x1={CENTER}
                  y1={CENTER}
                  x2={x2}
                  y2={y2}
                  stroke="currentColor"
                  className="text-border/40"
                  strokeWidth={1}
                />
              );
            })}

            {/* 数据多边形渐变与填充 */}
            <defs>
              <linearGradient id="radarPulseGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.45" />
                <stop offset="100%" stopColor="#10b981" stopOpacity="0.30" />
              </linearGradient>
            </defs>

            <polygon
              data-testid="radar-data-polygon"
              points={radarPoints.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')}
              fill="url(#radarPulseGradient)"
              stroke="#3b82f6"
              strokeWidth={2}
              className="transition-all duration-200"
            />

            {/* 顶点指示点 */}
            {radarPoints.map((pt, idx) => (
              <circle
                key={`dot-${idx}`}
                cx={pt.x}
                cy={pt.y}
                r={3.5}
                className="fill-blue-500 stroke-background stroke-2"
              />
            ))}
          </svg>
        </div>
      </div>

      {/* 5 维微调滑块区域 */}
      <div className="flex-1 space-y-4 overflow-y-auto pr-1">
        {DIMENSIONS.map((dim) => {
          const Icon = dim.icon;
          const currentVal = values[dim.key] ?? 1.0;
          return (
            <div key={dim.key} className="space-y-1.5 rounded-lg border border-border/40 bg-muted/20 p-3">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5 font-medium text-foreground">
                  <Icon className="h-3.5 w-3.5 text-primary" />
                  <span>{t(dim.labelKey)}</span>
                  <span className="text-[10px] text-muted-foreground">({t(dim.hintKey)})</span>
                </div>
                <span className="font-mono text-xs font-semibold text-primary">{currentVal.toFixed(2)}x</span>
              </div>
              <input
                type="range"
                min={MIN_BOUND}
                max={MAX_BOUND}
                step={0.05}
                value={currentVal}
                disabled={locked}
                onChange={(e) => onValueChange(dim.key, parseFloat(e.target.value))}
                data-testid={`slider-${dim.key}`}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-muted accent-primary disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
          );
        })}
      </div>

      {/* 底部重置与说明栏 */}
      <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-4">
        <button
          type="button"
          data-testid="radar-reset-button"
          onClick={onReset}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          <span>{t('resetBaseline')}</span>
        </button>
        <span className="text-[11px] text-muted-foreground">{locked ? t('modeManual') : t('modeDynamic')}</span>
      </div>
    </aside>
  );
};
