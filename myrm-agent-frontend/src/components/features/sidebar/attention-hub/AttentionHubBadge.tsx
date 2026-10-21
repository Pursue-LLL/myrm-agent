'use client';

/**
 * [INPUT]
 * - @/components/features/sidebar/attention-hub/useAttentionHubStore
 * - lucide-react (POS: Vector icons, zero native emojis)
 *
 * [OUTPUT]
 * - AttentionHubBadge (POS: Permanent sidebar attention indicator with pulse badge)
 *
 * [POS]
 * Implementation for Item 189 sidebar entry point.
 * Shows live blocking count and alerts users when high-priority approvals or tasks require intervention.
 */

import React, { memo, useMemo, useCallback } from 'react';
import { Bell, AlertCircle } from 'lucide-react';
import { useAttentionHubStore } from './useAttentionHubStore';

interface AttentionHubBadgeProps {
  readonly className?: string;
  readonly compact?: boolean;
}

export const AttentionHubBadge = memo(function AttentionHubBadge({
  className = '',
  compact = false,
}: AttentionHubBadgeProps) {
  const items = useAttentionHubStore((s) => s.items);
  const isPanelOpen = useAttentionHubStore((s) => s.isPanelOpen);
  const togglePanel = useAttentionHubStore((s) => s.togglePanel);

  const stats = useMemo(() => {
    let actionRequiredCount = 0;
    let hasUrgent = false;

    for (const item of items) {
      if (item.actionRequired) {
        actionRequiredCount += 1;
        if (item.priority === 'urgent') {
          hasUrgent = true;
        }
      }
    }

    return { actionRequiredCount, hasUrgent };
  }, [items]);

  const handleClick = useCallback(() => {
    togglePanel();
  }, [togglePanel]);

  const badgeColorClass = useMemo(() => {
    if (stats.hasUrgent) {
      return 'bg-rose-500 text-white animate-pulse';
    }
    if (stats.actionRequiredCount > 0) {
      return 'bg-amber-500 text-neutral-900 font-semibold';
    }
    return 'bg-neutral-700 text-neutral-300';
  }, [stats.hasUrgent, stats.actionRequiredCount]);

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={`注意力中枢：${stats.actionRequiredCount}项待处理`}
      aria-expanded={isPanelOpen}
      aria-haspopup="dialog"
      className={`relative flex items-center gap-2 px-2.5 py-1.5 rounded-lg border transition-all text-xs font-medium focus:outline-none focus:ring-1 focus:ring-rose-500 ${
        isPanelOpen
          ? 'bg-neutral-800 border-neutral-700 text-neutral-100'
          : 'bg-neutral-900/80 border-neutral-800 text-neutral-300 hover:bg-neutral-800/80 hover:text-white'
      } ${className}`}
    >
      <div className="relative flex items-center justify-center">
        {stats.hasUrgent ? (
          <AlertCircle className="w-4 h-4 text-rose-400" aria-hidden="true" />
        ) : (
          <Bell className="w-4 h-4 text-neutral-400" aria-hidden="true" />
        )}
      </div>

      {!compact ? <span>注意力中枢</span> : null}

      {stats.actionRequiredCount > 0 ? (
        <span
          className={`flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] leading-none ${badgeColorClass}`}
        >
          {stats.actionRequiredCount > 99 ? '99+' : stats.actionRequiredCount}
        </span>
      ) : null}
    </button>
  );
});
