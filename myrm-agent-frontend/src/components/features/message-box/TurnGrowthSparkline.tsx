'use client';

/**
 * [INPUT]
 * - useContextWatermarkMetrics::ContextWatermarkMetrics (POS: Watermark tokens & weather tier.)
 * - next-intl::useTranslations (POS: Internationalization.)
 *
 * [OUTPUT]
 * - TurnGrowthSparkline: compact SVG sparkline curve visualizer with delta badge and semantic weather status.
 *
 * [POS]
 * Visualizes turn-by-turn context growth trajectory (last 12 turns), delta vs previous turn,
 * and dual-theme weather tier badge to provide intuitive compression forecasting.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import type { ContextWatermarkMetrics } from './useContextWatermarkMetrics';

interface TurnGrowthSparklineProps {
  metrics: ContextWatermarkMetrics;
  className?: string;
  width?: number;
  height?: number;
  showBadge?: boolean;
}

function formatTokens(tokens: number): string {
  const abs = Math.abs(tokens);
  if (abs >= 1000000) {
    const val = abs / 1000000;
    const formatted = val % 1 === 0 ? val.toFixed(0) : val.toFixed(1);
    return `${tokens < 0 ? '-' : ''}${formatted}M`;
  }
  if (abs >= 1000) {
    const val = abs / 1000;
    const formatted = val % 1 === 0 ? val.toFixed(0) : val.toFixed(1);
    return `${tokens < 0 ? '-' : ''}${formatted}K`;
  }
  return tokens.toString();
}

export default function TurnGrowthSparkline({
  metrics,
  className = '',
  width = 180,
  height = 36,
  showBadge = true,
}: TurnGrowthSparklineProps) {
  const t = useTranslations('chat.contextUsage');
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const { historyTurnTokens, deltaTokens, hasDelta, weatherBadgeClass, weatherLabelKey } = metrics;

  if (historyTurnTokens.length === 0) {
    return null;
  }

  const paddingX = 6;
  const paddingY = 6;
  const effectiveWidth = Math.max(width - paddingX * 2, 20);
  const effectiveHeight = Math.max(height - paddingY * 2, 10);

  const minVal = Math.min(...historyTurnTokens);
  const maxVal = Math.max(...historyTurnTokens);
  const range = maxVal - minVal || 1;

  const points = historyTurnTokens.map((val, idx) => {
    const x =
      historyTurnTokens.length > 1
        ? paddingX + (idx / (historyTurnTokens.length - 1)) * effectiveWidth
        : width / 2;
    // Note: SVG y=0 is at top, so higher token values get smaller y
    const normalizedY = (val - minVal) / range;
    const y = height - paddingY - normalizedY * effectiveHeight;
    return { x, y, val, idx };
  });

  const pathD = points.reduce((acc, pt, idx) => {
    return idx === 0 ? `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}` : `${acc} L ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
  }, '');

  const areaD =
    points.length > 1
      ? `${pathD} L ${points[points.length - 1].x.toFixed(1)} ${height} L ${points[0].x.toFixed(1)} ${height} Z`
      : '';

  const gradientId = `sparkline-gradient-${metrics.weatherTier}`;

  const renderDeltaBadge = () => {
    if (!hasDelta) {
      return null;
    }
    if (deltaTokens > 0) {
      return (
        <span
          data-testid="sparkline-delta-badge"
          className="text-[10px] font-medium text-amber-600 dark:text-amber-400 tabular-nums"
        >
          {t('deltaPositive', { tokens: formatTokens(deltaTokens) })}
        </span>
      );
    }
    if (deltaTokens < 0) {
      return (
        <span
          data-testid="sparkline-delta-badge"
          className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400 tabular-nums"
        >
          {t('deltaNegative', { tokens: formatTokens(Math.abs(deltaTokens)) })}
        </span>
      );
    }
    return (
      <span
        data-testid="sparkline-delta-badge"
        className="text-[10px] font-medium text-muted-foreground tabular-nums"
      >
        {t('deltaZero')}
      </span>
    );
  };

  return (
    <div
      data-testid="turn-growth-sparkline"
      className={`flex flex-col gap-1.5 p-2 rounded-lg bg-muted/20 border border-border/40 ${className}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium text-muted-foreground">{t('growthTrend')}</span>
        {showBadge && (
          <span
            data-testid="sparkline-weather-badge"
            className={`text-[9px] px-1.5 py-0.5 rounded-full border font-medium transition-colors ${weatherBadgeClass}`}
          >
            {t(weatherLabelKey)}
          </span>
        )}
      </div>

      <div className="relative flex items-center justify-center">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          className="overflow-visible"
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.25" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {areaD && (
            <path
              d={areaD}
              fill={`url(#${gradientId})`}
              className="text-primary-dark/30 dark:text-primary-light/30"
            />
          )}

          <path
            d={pathD}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.75}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-primary-dark dark:text-primary-light"
          />

          {points.map((pt) => {
            const isLatest = pt.idx === points.length - 1;
            const isHovered = pt.idx === hoveredIndex;
            return (
              <circle
                key={pt.idx}
                cx={pt.x}
                cy={pt.y}
                r={isHovered ? 3.5 : isLatest ? 2.5 : 1.5}
                className={
                  isLatest
                    ? 'fill-primary-dark dark:fill-primary-light stroke-background stroke-1'
                    : isHovered
                      ? 'fill-foreground stroke-background stroke-1'
                      : 'fill-muted-foreground/50'
                }
                onMouseEnter={() => setHoveredIndex(pt.idx)}
                onMouseLeave={() => setHoveredIndex(null)}
              />
            );
          })}
        </svg>

        {hoveredIndex !== null && points[hoveredIndex] && (
          <div
            data-testid="sparkline-tooltip"
            className="absolute -top-6 px-1.5 py-0.5 rounded bg-popover text-popover-foreground text-[9px] font-medium border border-border shadow-xs pointer-events-none tabular-nums"
            style={{
              left: `${points[hoveredIndex].x}px`,
              transform: 'translateX(-50%)',
            }}
          >
            {formatTokens(points[hoveredIndex].val)}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between text-[10px] pt-1 border-t border-border/30">
        <span className="text-muted-foreground">
          {historyTurnTokens.length} {t('history')}
        </span>
        {renderDeltaBadge()}
      </div>
    </div>
  );
}
