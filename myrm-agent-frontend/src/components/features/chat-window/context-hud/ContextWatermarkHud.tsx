/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Consistent vector icons)
 * - @/components/features/chat-window/context-hud/contextHudTypes
 * - @/components/features/chat-window/context-hud/contextHudEngine
 * - @/components/features/chat-window/context-hud/useContextHudStore
 *
 * [OUTPUT]
 * - ContextWatermarkHud (POS: 6-metrics health HUD and context watermark indicator)
 *
 * [POS]
 * Primary HUD capsule for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite.
 * Renders the 6 key numbers: Input tokens (↑), Output tokens (↓), Read cache tokens (R K),
 * Cache hit rate (CH%), Watermark %, and Auto-compact status badge.
 */

import React from 'react';
import {
  ArrowUp,
  ArrowDown,
  Zap,
  Percent,
  Gauge,
  Sparkles,
  ChevronDown,
} from 'lucide-react';
import { useContextHudStore } from './useContextHudStore';
import {
  formatTokenMetric,
  formatPercentage,
  resolveWatermarkColor,
  computeContextHudMetrics,
} from './contextHudEngine';

export interface ContextWatermarkHudProps {
  readonly chatId?: string;
  readonly compact?: boolean;
  readonly className?: string;
  readonly onOpenDiagnostics?: () => void;
}

const defaultZeroMetrics = computeContextHudMetrics({
  inputTokens: 0,
  outputTokens: 0,
  cachedReadTokens: 0,
});

export const ContextWatermarkHud: React.FC<ContextWatermarkHudProps> = ({
  chatId,
  compact = false,
  className = '',
  onOpenDiagnostics,
}) => {
  const activeChatId = useContextHudStore((state) => state.activeChatId);
  const metricsByChatId = useContextHudStore((state) => state.metricsByChatId);
  const togglePopover = useContextHudStore((state) => state.togglePopover);

  const targetChatId = chatId ?? activeChatId;
  const metrics = (targetChatId ? metricsByChatId[targetChatId] : undefined) ?? defaultZeroMetrics;

  const colorStyles = resolveWatermarkColor(metrics.watermarkLevel);

  const handleOpen = () => {
    if (onOpenDiagnostics) {
      onOpenDiagnostics();
    } else {
      togglePopover(true);
    }
  };

  return (
    <div
      data-testid="context-watermark-hud"
      className={`inline-flex items-center gap-2 ${className}`}
    >
      <button
        type="button"
        onClick={handleOpen}
        data-testid="context-hud-trigger-button"
        title="点击查看 Prompt Cache 命中归因与上下文优化诊断"
        aria-label="查看上下文水位与缓存归因诊断"
        className="inline-flex items-center gap-2.5 rounded-full border border-border/80 bg-muted/30 px-3 py-1 text-xs font-medium text-foreground transition-all hover:bg-accent hover:border-accent-foreground/20 shadow-sm"
      >
        {/* 1 & 2: 输入/输出 Token 指标 */}
        <div className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
          <span className="flex items-center" title={`累计输入: ${metrics.inputTokens} Tokens`}>
            <ArrowUp className="w-3 h-3 text-sky-500 mr-0.5" />
            <span>{formatTokenMetric(metrics.inputTokens)}</span>
          </span>
          <span className="text-border">/</span>
          <span className="flex items-center" title={`累计输出: ${metrics.outputTokens} Tokens`}>
            <ArrowDown className="w-3 h-3 text-emerald-500 mr-0.5" />
            <span>{formatTokenMetric(metrics.outputTokens)}</span>
          </span>
        </div>

        {/* 3 & 4: 缓存命中 Token 与 命中率 (CH%) */}
        {!compact ? (
          <>
            <span className="text-border">|</span>
            <div className="flex items-center gap-1.5 font-mono text-[11px]">
              <span
                className="flex items-center text-amber-600 dark:text-amber-400"
                title={`命中缓存 Token: ${metrics.cachedReadTokens}`}
              >
                <Zap className="w-3 h-3 mr-0.5 fill-amber-500/20" />
                <span>{formatTokenMetric(metrics.cachedReadTokens)}</span>
              </span>
              <span
                className="flex items-center text-indigo-600 dark:text-indigo-400 font-semibold"
                title={`缓存命中率: ${metrics.cacheHitRate}%`}
              >
                <Percent className="w-3 h-3 mr-0.5" />
                <span>{formatPercentage(metrics.cacheHitRate)}</span>
              </span>
            </div>
          </>
        ) : null}

        {/* 5: 上下文占用水位与进度条 */}
        <span className="text-border">|</span>
        <div className="flex items-center gap-1.5">
          <div className="flex items-center gap-1 font-mono text-[11px]">
            <Gauge className={`w-3.5 h-3.5 ${colorStyles.textClass}`} />
            <span className={`font-semibold ${colorStyles.textClass}`}>
              {formatPercentage(metrics.watermarkPercentage)}
            </span>
          </div>

          <div className="w-12 hidden sm:block">
            <progress
              value={metrics.watermarkPercentage}
              max={100}
              aria-label="上下文占用水位"
              className={`h-1.5 w-full overflow-hidden rounded-full bg-secondary ${colorStyles.progressClass}`}
            />
          </div>
        </div>

        {/* 6: 自动压缩状态胶囊 */}
        {metrics.autoCompactState !== 'disabled' ? (
          <div
            className={`hidden md:inline-flex items-center gap-0.5 rounded-full border px-1.5 py-0.2 text-[10px] font-medium ${
              metrics.autoCompactState === 'active'
                ? 'bg-primary/10 text-primary border-primary/20'
                : 'bg-muted text-muted-foreground border-border/40'
            }`}
            title={`自动压缩状态: ${metrics.autoCompactState}`}
          >
            <Sparkles className="w-2.5 h-2.5" />
            <span>auto</span>
          </div>
        ) : null}

        <ChevronDown className="w-3 h-3 text-muted-foreground/60 ml-0.5" />
      </button>
    </div>
  );
};
