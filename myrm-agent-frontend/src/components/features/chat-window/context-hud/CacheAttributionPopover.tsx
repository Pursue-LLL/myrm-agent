/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Consistent vector icons)
 * - @/components/features/chat-window/context-hud/contextHudTypes
 * - @/components/features/chat-window/context-hud/contextHudEngine
 * - @/components/features/chat-window/context-hud/useContextHudStore
 *
 * [OUTPUT]
 * - CacheAttributionPopover (POS: Diagnostic popover for prompt cache attribution and optimization)
 *
 * [POS]
 * Primary diagnostic modal for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite.
 * Explains cache miss root causes, provides actionable prefix guidance, and enables 1-click compaction.
 */

import React, { useEffect, useCallback } from 'react';
import {
  Zap,
  X,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Lightbulb,
  Minimize2,
} from 'lucide-react';
import type { CacheAttributionReport } from './contextHudTypes';
import { formatTokenMetric } from './contextHudEngine';
import { useContextHudStore } from './useContextHudStore';

export interface CacheAttributionPopoverProps {
  readonly chatId?: string;
  readonly onClose?: () => void;
  readonly className?: string;
}

const defaultReport: CacheAttributionReport = {
  reason: 'none',
  reasonTitle: '缓存平稳运行中',
  description: 'Prompt Cache 链路就绪，前缀保持稳定。',
  suggestion: '保持当前会话前缀连贯即可享受极速响应。',
  estimatedTokenSavings: 0,
  score: 100,
};

export const CacheAttributionPopover: React.FC<CacheAttributionPopoverProps> = ({
  chatId,
  onClose,
  className = '',
}) => {
  const isPopoverOpen = useContextHudStore((state) => state.isPopoverOpen);
  const activeChatId = useContextHudStore((state) => state.activeChatId);
  const attributionReports = useContextHudStore((state) => state.attributionReports);
  const metricsByChatId = useContextHudStore((state) => state.metricsByChatId);
  const togglePopover = useContextHudStore((state) => state.togglePopover);
  const triggerAutoCompact = useContextHudStore((state) => state.triggerAutoCompact);

  const targetChatId = chatId ?? activeChatId ?? 'default';
  const report = attributionReports[targetChatId] ?? defaultReport;
  const metrics = metricsByChatId[targetChatId];

  const handleClose = useCallback(() => {
    togglePopover(false);
    if (onClose) {
      onClose();
    }
  }, [togglePopover, onClose]);

  // 支持键盘 Escape 关闭
  useEffect(() => {
    if (!isPopoverOpen) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isPopoverOpen, handleClose]);

  if (!isPopoverOpen) {
    return null;
  }

  const isHealthy = report.score >= 80;
  const isWarning = report.score >= 50 && report.score < 80;

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="cache-attribution-popover-title"
      data-testid="cache-attribution-popover"
      onCancel={handleClose}
      className={`fixed inset-0 z-50 m-0 flex h-full w-full max-h-none max-w-none items-center justify-center bg-transparent p-4 border-none ${className}`}
    >
      {/* 语义化全屏背景遮罩按钮 */}
      <button
        type="button"
        aria-label="关闭背景遮罩"
        data-testid="cache-attribution-backdrop"
        onClick={handleClose}
        className="fixed inset-0 -z-10 h-full w-full bg-black/60 backdrop-blur-sm cursor-default border-none p-0 m-0"
      />

      <div className="relative w-full max-w-md flex flex-col rounded-xl border border-border bg-card shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* 对话框头部 */}
        <div className="flex items-center justify-between border-b border-border/80 px-5 py-3.5 bg-muted/40">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500 fill-amber-500/20" />
            <h3 id="cache-attribution-popover-title" className="text-sm font-semibold text-foreground">
              Prompt Cache 命中归因与诊断
            </h3>
          </div>

          <button
            type="button"
            onClick={handleClose}
            title="关闭诊断卡片"
            aria-label="关闭诊断卡片"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 核心归因状态卡片 */}
        <div className="p-5 space-y-4">
          <div className="flex items-start gap-3 rounded-lg border border-border/70 bg-muted/20 p-3.5">
            {isHealthy ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
            ) : isWarning ? (
              <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
            )}

            <div className="flex-1">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-foreground">
                  {report.reasonTitle}
                </h4>
                <span
                  className={`text-xs font-mono font-bold px-2 py-0.5 rounded-full border ${
                    isHealthy
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                      : isWarning
                        ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                        : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
                  }`}
                >
                  健康分 {report.score}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                {report.description}
              </p>
            </div>
          </div>

          {/* 优化建议卡片 */}
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-3.5 text-xs">
            <div className="flex items-center gap-1.5 font-semibold text-primary mb-1">
              <Lightbulb className="w-3.5 h-3.5" />
              <span>前缀缓存优化指导</span>
            </div>
            <p className="text-foreground/90 leading-relaxed">
              {report.suggestion}
            </p>
            {report.estimatedTokenSavings > 0 ? (
              <div className="mt-2 text-[11px] text-muted-foreground">
                预计可节约开销: ≈{' '}
                <span className="font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                  {formatTokenMetric(report.estimatedTokenSavings)} Tokens
                </span>
              </div>
            ) : null}
          </div>

          {/* 遥测概览指标小卡 */}
          {metrics ? (
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md border border-border/60 bg-muted/30 p-2.5">
                <span className="text-[11px] text-muted-foreground">当前上下文占用</span>
                <div className="text-sm font-bold font-mono text-foreground mt-0.5">
                  {formatTokenMetric(metrics.usedTokens)} / {formatTokenMetric(metrics.contextLimit)}
                </div>
              </div>
              <div className="rounded-md border border-border/60 bg-muted/30 p-2.5">
                <span className="text-[11px] text-muted-foreground">缓存命中率 (CH%)</span>
                <div className="text-sm font-bold font-mono text-indigo-600 dark:text-indigo-400 mt-0.5">
                  {metrics.cacheHitRate}%
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* 底部按钮栏 */}
        <div className="flex items-center justify-between border-t border-border px-5 py-3 bg-muted/30">
          <button
            type="button"
            onClick={() => {
              triggerAutoCompact(targetChatId);
            }}
            title="一键触发上下文自动修剪压缩"
            aria-label="一键触发自动压缩"
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors shadow-sm"
          >
            <Minimize2 className="w-3.5 h-3.5 text-primary" />
            <span>一键主动修剪</span>
          </button>

          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg bg-secondary px-4 py-1.5 text-xs font-medium text-secondary-foreground hover:bg-secondary/80 transition-colors"
          >
            完成查看
          </button>
        </div>
      </div>
    </dialog>
  );
};
