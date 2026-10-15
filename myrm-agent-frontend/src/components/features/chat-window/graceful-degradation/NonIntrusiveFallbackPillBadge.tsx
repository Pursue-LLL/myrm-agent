import React, { useState } from 'react';
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock,
  Info,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react';
import { generateFallbackPillText } from './gracefulDegradationEngine';
import { DegradationEvent } from './gracefulDegradationTypes';
import { useGracefulDegradationStore } from './useGracefulDegradationStore';

interface NonIntrusiveFallbackPillBadgeProps {
  event: DegradationEvent;
  onRetryProbe?: (event: DegradationEvent) => void;
  className?: string;
}

export const NonIntrusiveFallbackPillBadge: React.FC<
  NonIntrusiveFallbackPillBadgeProps
> = ({ event, onRetryProbe, className = '' }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const resolveDegradation = useGracefulDegradationStore(
    (state) => state.resolveDegradation,
  );

  const handleRetry = async () => {
    setIsRetrying(true);
    if (onRetryProbe) {
      onRetryProbe(event);
    }
    // 模拟探测反馈
    setTimeout(() => {
      setIsRetrying(false);
    }, 600);
  };

  const pillText = generateFallbackPillText(event);

  return (
    <div
      data-testid={`fallback-pill-${event.id}`}
      className={`my-1.5 inline-block w-full max-w-xl text-left select-none transition-all ${className}`}
    >
      {/* 紧凑胶囊微徽章 */}
      <div className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-700 dark:text-amber-300 backdrop-blur-xs">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" />
        <span className="min-w-0 flex-1 truncate font-medium">{pillText}</span>

        <button
          type="button"
          onClick={() => {
            setIsExpanded(!isExpanded);
          }}
          aria-expanded={isExpanded}
          aria-label={isExpanded ? '收起降级详情' : '展开降级详情'}
          className="flex items-center gap-0.5 rounded px-1 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400 hover:bg-amber-500/15 transition-colors"
        >
          <span>{isExpanded ? '收起详情' : '查看详情'}</span>
          {isExpanded ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
        </button>

        <button
          type="button"
          onClick={() => {
            resolveDegradation(event.id);
          }}
          aria-label="关闭降级说明徽标"
          className="rounded p-0.5 text-amber-600/70 hover:text-amber-700 dark:text-amber-400/70 dark:hover:text-amber-300"
        >
          <X className="h-3 w-3" />
        </button>
      </div>

      {/* 展开的白盒自愈与技术细节面板 */}
      {isExpanded && (
        <div
          data-testid="fallback-detail-panel"
          className="mt-1.5 rounded-lg border border-amber-500/20 bg-background/95 p-3 text-xs shadow-md backdrop-blur-md dark:bg-muted/80"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="flex items-center gap-1.5 font-semibold text-foreground">
                <Info className="h-3.5 w-3.5 text-amber-500" />
                <span>{event.title}</span>
              </div>
              <p className="mt-1 text-muted-foreground leading-relaxed">
                {event.explanation}
              </p>
            </div>
          </div>

          <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border/40 text-[11px]">
            <div className="flex items-center gap-3 text-muted-foreground">
              <span className="flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-400">
                <ShieldCheck className="h-3 w-3" />
                {event.fallbackActionLabel}
              </span>
              {event.recoveryEtaSec !== undefined && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  断路器自愈冷却 ~{event.recoveryEtaSec}s
                </span>
              )}
            </div>

            <button
              type="button"
              onClick={handleRetry}
              disabled={isRetrying}
              className="flex items-center gap-1 rounded border border-border/60 bg-background px-2 py-0.5 text-[11px] font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              <RefreshCw
                className={`h-2.5 w-2.5 ${isRetrying ? 'animate-spin' : ''}`}
              />
              <span>{isRetrying ? '探测中...' : '重新探测'}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
