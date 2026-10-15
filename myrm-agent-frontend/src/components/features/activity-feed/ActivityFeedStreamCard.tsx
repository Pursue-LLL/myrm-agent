'use client';

/**
 * [INPUT]
 * - @/components/features/activity-feed/activityFeedTypes
 * - @/components/features/activity-feed/activityFeedEngine
 * - @/components/features/activity-feed/useActivityFeedStore
 * - lucide-react (POS: Vector icons, zero native emojis)
 *
 * [OUTPUT]
 * - ActivityFeedStreamCard (POS: Multi-system activity stream card with auto-evaporation progress)
 *
 * [POS]
 * Implementation for Item 190 individual feed item card.
 * Handles autonomous resolution fade-out cues, executive bottlenecks, and one-click approvals.
 */

import React, { memo, useMemo, useEffect, useState } from 'react';
import {
  Mail,
  Calendar,
  MessageSquare,
  ShieldAlert,
  Clock,
  Kanban,
  Check,
  X,
  Sparkles,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import type { ActivityFeedItem, FeedSourceSystem } from './activityFeedTypes';
import { getSourceSystemMeta, computeEvaporationProgress } from './activityFeedEngine';
import { useActivityFeedStore } from './useActivityFeedStore';

interface ActivityFeedStreamCardProps {
  readonly item: ActivityFeedItem;
  readonly className?: string;
  readonly onApprove?: (id: string) => void;
  readonly onReject?: (id: string) => void;
}

export const ActivityFeedStreamCard = memo(function ActivityFeedStreamCard({
  item,
  className = '',
  onApprove,
  onReject,
}: ActivityFeedStreamCardProps) {
  const isPaused = useActivityFeedStore((s) => s.isEvaporationPaused);
  const evaporateItem = useActivityFeedStore((s) => s.evaporateItem);
  const humanDecide = useActivityFeedStore((s) => s.humanDecide);

  const [progress, setProgress] = useState(() =>
    computeEvaporationProgress(item.resolvedAt, item.evaporationTtlMs),
  );

  const sourceMeta = useMemo(() => getSourceSystemMeta(item.sourceSystem), [item.sourceSystem]);

  // Handle continuous evaporation progress updates
  useEffect(() => {
    if (item.status !== 'evaporating' || isPaused) {
      return;
    }

    const interval = setInterval(() => {
      const p = computeEvaporationProgress(item.resolvedAt, item.evaporationTtlMs);
      setProgress(p);

      if (p >= 1) {
        clearInterval(interval);
        evaporateItem(item.id);
      }
    }, 100);

    return () => clearInterval(interval);
  }, [item.id, item.status, item.resolvedAt, item.evaporationTtlMs, isPaused, evaporateItem]);

  const renderSourceIcon = (source: FeedSourceSystem) => {
    switch (source) {
      case 'email': {
        return <Mail className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />;
      }
      case 'calendar': {
        return <Calendar className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />;
      }
      case 'messaging': {
        return <MessageSquare className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />;
      }
      case 'approval': {
        return <ShieldAlert className="w-3.5 h-3.5 text-rose-400" aria-hidden="true" />;
      }
      case 'cron': {
        return <Clock className="w-3.5 h-3.5 text-purple-400" aria-hidden="true" />;
      }
      case 'kanban': {
        return <Kanban className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />;
      }
    }
  };

  const handleApprove = () => {
    humanDecide(item.id, true);
    if (onApprove) {
      onApprove(item.id);
    }
  };

  const handleReject = () => {
    humanDecide(item.id, false);
    if (onReject) {
      onReject(item.id);
    }
  };

  const isHumanBlocking =
    item.autonomyTier === 'human_decision_required' && item.status === 'pending_decision';
  const isEvaporating = item.status === 'evaporating';

  return (
    <article
      aria-label={`事项：${item.title}`}
      className={`relative rounded-xl border p-3.5 transition-all duration-300 text-xs overflow-hidden ${
        isHumanBlocking
          ? 'bg-rose-950/20 border-rose-500/40 shadow-sm'
          : isEvaporating
          ? 'bg-neutral-900/60 border-neutral-800 opacity-80'
          : 'bg-neutral-900/80 border-neutral-800 hover:border-neutral-700'
      } ${className}`}
    >
      {/* Top Banner: Source System & Status */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-neutral-800 text-[11px] font-medium text-neutral-300 border border-neutral-700/60">
            {renderSourceIcon(item.sourceSystem)}
            <span>{sourceMeta.label}</span>
          </span>
          <span className="text-[11px] font-mono text-neutral-500">#{item.sourceRefId}</span>
        </div>

        {isHumanBlocking ? (
          <span className="flex items-center gap-1 text-[11px] font-semibold text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-full border border-rose-500/20">
            <AlertCircle className="w-3 h-3" aria-hidden="true" />
            <span>待你拍板</span>
          </span>
        ) : isEvaporating ? (
          <span className="flex items-center gap-1 text-[11px] text-sky-400 bg-sky-500/10 px-2 py-0.5 rounded-full">
            <Sparkles className="w-3 h-3 animate-spin" aria-hidden="true" />
            <span>自主处理完成 · 即将蒸发</span>
          </span>
        ) : item.status === 'autonomous_processing' ? (
          <span className="flex items-center gap-1 text-[11px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full">
            <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
            <span>Agent 自治推进中</span>
          </span>
        ) : (
          <span className="text-[10px] text-neutral-500">
            {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>

      {/* Title & Summary */}
      <div className="mt-2.5">
        <h3 className="font-semibold text-neutral-100 text-sm leading-tight">{item.title}</h3>
        <p className="mt-1 text-neutral-400 text-xs leading-relaxed line-clamp-2">{item.summary}</p>
      </div>

      {/* Snippet Detail */}
      {item.payloadSnippet ? (
        <div className="mt-2 p-2 rounded bg-neutral-950/60 font-mono text-[11px] text-neutral-400 border border-neutral-800/80 truncate">
          {item.payloadSnippet}
        </div>
      ) : null}

      {/* Bottom Action Area */}
      {isHumanBlocking ? (
        <div className="mt-3 pt-2.5 border-t border-rose-500/20 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={handleReject}
            className="flex items-center gap-1 px-3 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors"
          >
            <X className="w-3.5 h-3.5" aria-hidden="true" />
            <span>驳回</span>
          </button>
          <button
            type="button"
            onClick={handleApprove}
            className="flex items-center gap-1 px-3 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white font-medium transition-colors"
          >
            <Check className="w-3.5 h-3.5" aria-hidden="true" />
            <span>确认放行</span>
          </button>
        </div>
      ) : null}

      {/* Evaporating Progress Bar */}
      {isEvaporating ? (
        <div className="mt-3">
          <div className="flex items-center justify-between text-[10px] text-neutral-500 pb-1">
            <span>自动蒸发中...</span>
            <span>{Math.round((1 - progress) * 100)}%</span>
          </div>
          <progress
            className="w-full h-1 rounded-full overflow-hidden block [&::-webkit-progress-bar]:bg-neutral-800 [&::-webkit-progress-value]:bg-sky-500 [&::-moz-progress-bar]:bg-sky-500"
            value={Math.round((1 - progress) * 100)}
            max={100}
            aria-label="自动蒸发倒计时进度"
          />
        </div>
      ) : null}
    </article>
  );
});
