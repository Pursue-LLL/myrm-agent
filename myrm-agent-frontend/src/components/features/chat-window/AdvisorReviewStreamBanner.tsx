'use client';

/**
 * [INPUT]: AdvisorReviewItem[] 或单个 AdvisorReviewItem, 以及操作回调函数
 * [OUTPUT]: 渲染三级干预（aside/concern/blocker）的双模型审查旁路横幅，支持 blocker 熔断交互与审查细节折叠
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/AdvisorReviewStreamBanner.tsx
 */

import React, { useState } from 'react';
import {
  ShieldAlert,
  AlertTriangle,
  Info,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  Bot,
  Zap,
} from 'lucide-react';

export type AdvisorInterventionLevel = 'aside' | 'concern' | 'blocker';

export interface AdvisorReviewItem {
  reviewId: string;
  stepId: string;
  interventionLevel: AdvisorInterventionLevel;
  shouldPause: boolean;
  reasoning: string;
  proposedAction: string;
  alternativeAction?: string;
  confidenceScore: number;
  advisorModel?: string;
  durationMs?: number;
  timestamp?: string;
}

export interface AdvisorReviewStreamBannerProps {
  currentReview?: AdvisorReviewItem | null;
  reviewHistory?: AdvisorReviewItem[];
  onAcceptIntervention?: (review: AdvisorReviewItem) => void;
  onDismissIntervention?: (review: AdvisorReviewItem) => void;
  onClearHistory?: () => void;
  className?: string;
}

const LEVEL_CONFIG: Record<
  AdvisorInterventionLevel,
  {
    label: string;
    badgeBg: string;
    badgeText: string;
    border: string;
    bg: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  aside: {
    label: '旁路提示 (Aside)',
    badgeBg: 'bg-blue-500/10 dark:bg-blue-400/20',
    badgeText: 'text-blue-600 dark:text-blue-400',
    border: 'border-blue-200 dark:border-blue-900/60',
    bg: 'bg-blue-50/70 dark:bg-blue-950/30',
    icon: Info,
  },
  concern: {
    label: '预警关注 (Concern)',
    badgeBg: 'bg-amber-500/10 dark:bg-amber-400/20',
    badgeText: 'text-amber-600 dark:text-amber-400',
    border: 'border-amber-200 dark:border-amber-900/60',
    bg: 'bg-amber-50/70 dark:bg-amber-950/30',
    icon: AlertTriangle,
  },
  blocker: {
    label: '阻断熔断 (Blocker)',
    badgeBg: 'bg-rose-500/10 dark:bg-rose-400/20',
    badgeText: 'text-rose-600 dark:text-rose-400 font-semibold',
    border: 'border-rose-300 dark:border-rose-800',
    bg: 'bg-rose-50/90 dark:bg-rose-950/40',
    icon: ShieldAlert,
  },
};

export function AdvisorReviewStreamBanner({
  currentReview,
  reviewHistory = [],
  onAcceptIntervention,
  onDismissIntervention,
  onClearHistory,
  className = '',
}: AdvisorReviewStreamBannerProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const activeReview = currentReview ?? (reviewHistory.length > 0 ? reviewHistory[reviewHistory.length - 1] : null);

  if (!activeReview && reviewHistory.length === 0) {
    return null;
  }

  if (!activeReview) {
    return null;
  }

  const levelConf = LEVEL_CONFIG[activeReview.interventionLevel];
  const IconComponent = levelConf.icon;
  const isBlocker = activeReview.interventionLevel === 'blocker';

  return (
    <div
      data-testid="advisor-review-banner"
      className={`rounded-lg border transition-all duration-200 p-3 shadow-xs ${levelConf.bg} ${levelConf.border} ${className}`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="flex items-center gap-1.5 font-medium text-sm">
            <IconComponent className={`w-4 h-4 ${levelConf.badgeText}`} />
            <span className="text-zinc-800 dark:text-zinc-100 font-semibold">军师实时审查</span>
          </span>
          <span
            data-testid="advisor-level-badge"
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${levelConf.badgeBg} ${levelConf.badgeText}`}
          >
            {levelConf.label}
          </span>
          {activeReview.advisorModel && (
            <span className="flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
              <Bot className="w-3 h-3" />
              <span>{activeReview.advisorModel}</span>
            </span>
          )}
          {typeof activeReview.durationMs === 'number' && (
            <span className="flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
              <Zap className="w-3 h-3" />
              <span>{activeReview.durationMs}ms</span>
            </span>
          )}
          <span className="text-xs text-zinc-400 dark:text-zinc-500">
            置信度 {(activeReview.confidenceScore * 100).toFixed(0)}%
          </span>
        </div>

        <div className="flex items-center gap-2">
          {reviewHistory.length > 1 && (
            <button
              type="button"
              data-testid="toggle-history-btn"
              onClick={() => setShowHistory((prev) => !prev)}
              className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 underline cursor-pointer"
            >
              {showHistory ? '收起历史' : `查看历史 (${reviewHistory.length})`}
            </button>
          )}
          <button
            type="button"
            data-testid="toggle-expand-btn"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="p-1 rounded-sm hover:bg-black/5 dark:hover:bg-white/5 text-zinc-500 transition-colors"
            title={isExpanded ? '收起详情' : '展开详情'}
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Main summary / action row */}
      <div className="mt-2 text-xs text-zinc-700 dark:text-zinc-300">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="truncate">
            <span className="font-semibold text-zinc-900 dark:text-zinc-100">审查动作：</span>
            <code className="px-1 py-0.5 rounded bg-black/5 dark:bg-white/10 text-xs font-mono ml-1">
              {activeReview.proposedAction}
            </code>
          </div>

          {/* Action buttons on blocker or concern */}
          {isBlocker && (
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-xs font-medium text-rose-600 dark:text-rose-400 animate-pulse">
                主 Agent 已熔断暂停
              </span>
              {onAcceptIntervention && (
                <button
                  type="button"
                  data-testid="accept-intervention-btn"
                  onClick={() => onAcceptIntervention(activeReview)}
                  className="flex items-center gap-1 text-xs px-2.5 py-1 rounded bg-rose-600 text-white hover:bg-rose-700 active:scale-95 transition-all cursor-pointer font-medium"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  采纳军师方案并修正
                </button>
              )}
              {onDismissIntervention && (
                <button
                  type="button"
                  data-testid="dismiss-intervention-btn"
                  onClick={() => onDismissIntervention(activeReview)}
                  className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-rose-300 dark:border-rose-700 hover:bg-rose-100/50 dark:hover:bg-rose-900/40 text-rose-800 dark:text-rose-200 transition-all cursor-pointer"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  忽略并继续
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div data-testid="advisor-detail-section" className="mt-3 pt-2.5 border-t border-black/5 dark:border-white/10 text-xs space-y-2">
          <div>
            <span className="font-semibold text-zinc-800 dark:text-zinc-200">评估结论：</span>
            <p className="mt-0.5 text-zinc-600 dark:text-zinc-300 leading-relaxed whitespace-pre-wrap">
              {activeReview.reasoning}
            </p>
          </div>
          {activeReview.alternativeAction && (
            <div className="p-2 rounded bg-white/60 dark:bg-zinc-900/60 border border-black/5 dark:border-white/5">
              <span className="font-semibold text-emerald-700 dark:text-emerald-400">建议替代方案：</span>
              <p className="mt-0.5 text-zinc-700 dark:text-zinc-300 font-mono text-[11px]">
                {activeReview.alternativeAction}
              </p>
            </div>
          )}
          <div className="text-[11px] text-zinc-400 flex items-center justify-between">
            <span>步序号：{activeReview.stepId}</span>
            <span>审查单号：{activeReview.reviewId}</span>
          </div>
        </div>
      )}

      {/* History drawer list */}
      {showHistory && reviewHistory.length > 0 && (
        <div data-testid="advisor-history-section" className="mt-3 pt-2 border-t border-black/5 dark:border-white/10">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
              历次审查记录 ({reviewHistory.length})
            </span>
            {onClearHistory && (
              <button
                type="button"
                data-testid="clear-history-btn"
                onClick={onClearHistory}
                className="text-[11px] text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 cursor-pointer"
              >
                清空记录
              </button>
            )}
          </div>
          <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
            {reviewHistory.map((item) => {
              const itemConf = LEVEL_CONFIG[item.interventionLevel];
              return (
                <div
                  key={item.reviewId}
                  className="flex items-center justify-between gap-2 p-1.5 rounded bg-white/50 dark:bg-zinc-900/50 text-[11px] border border-black/5 dark:border-white/5"
                >
                  <div className="flex items-center gap-1.5 truncate">
                    <span className={`px-1.5 py-0.2 rounded text-[10px] ${itemConf.badgeBg} ${itemConf.badgeText}`}>
                      {item.interventionLevel}
                    </span>
                    <span className="font-mono truncate max-w-xs">{item.proposedAction}</span>
                  </div>
                  <span className="text-zinc-400 shrink-0">
                    {item.durationMs ? `${item.durationMs}ms` : ''}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default AdvisorReviewStreamBanner;
