'use client';

import React, { useMemo } from 'react';
import {
  Code,
  Compass,
  Cpu,
  Flame,
  Lock,
  Minimize2,
  RotateCcw,
  SlidersHorizontal,
  Unlock,
  X,
} from 'lucide-react';

export interface RadarDimensionValues {
  recency: number;
  actionability: number;
  technical_depth: number;
  conciseness: number;
  breadth: number;
}

export interface DynamicPreferenceRadarDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  values: RadarDimensionValues;
  locked: boolean;
  onValueChange: (dimension: keyof RadarDimensionValues, value: number) => void;
  onToggleLock: (nextLocked: boolean) => void;
  onReset: () => void;
  className?: string;
}

interface DimensionConfig {
  key: keyof RadarDimensionValues;
  label: string;
  subLabel: string;
  icon: React.ComponentType<{ className?: string }>;
}

const DIMENSIONS: DimensionConfig[] = [
  { key: 'recency', label: '时效脉冲', subLabel: '最新事件/日内分辨率', icon: Flame },
  { key: 'actionability', label: '代码实操', subLabel: '可执行脚本/实操步骤', icon: Code },
  { key: 'technical_depth', label: '架构深度', subLabel: '底层原理/演进根因', icon: Cpu },
  { key: 'conciseness', label: '精炼表达', subLabel: '直击要害/杜绝套话', icon: Minimize2 },
  { key: 'breadth', label: '全景视野', subLabel: '全局宏观/生态对比', icon: Compass },
];

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
  className = '',
}) => {
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

  if (!isOpen) {
    return null;
  }

  return (
    <aside
      data-testid="preference-radar-drawer"
      className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col border-l border-border bg-background/95 p-5 shadow-2xl backdrop-blur-md transition-all duration-300 dark:bg-zinc-950/95 sm:max-w-md ${className}`}
      aria-label="偏好拟合雷达看板"
    >
      {/* 顶部标题与操作栏 */}
      <div className="flex items-center justify-between border-b border-border/60 pb-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <SlidersHorizontal className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-foreground">在线偏好拟合雷达</h2>
            <p className="text-xs text-muted-foreground">连续重力衰减与多维权重微调</p>
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
            title={locked ? '已锁定：AI自动拟合暂停' : '未锁定：AI根据会话反馈自适应微调'}
          >
            {locked ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
            <span>{locked ? '已锁定' : '自适应中'}</span>
          </button>
          <button
            type="button"
            data-testid="radar-close-button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
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
                  <span>{dim.label}</span>
                  <span className="text-[10px] text-muted-foreground">({dim.subLabel})</span>
                </div>
                <span className="font-mono text-xs font-semibold text-primary">
                  {currentVal.toFixed(2)}x
                </span>
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
          <span>重置基准 (1.0x)</span>
        </button>
        <span className="text-[11px] text-muted-foreground">
          {locked ? '手动固定模式' : '动态学习模式'}
        </span>
      </div>
    </aside>
  );
};
