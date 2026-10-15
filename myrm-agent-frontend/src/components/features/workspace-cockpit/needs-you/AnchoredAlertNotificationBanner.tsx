'use client';

/**
 * 可锚定后台告警通知微横幅组件
 *
 * 在检测到未处理阻塞待办时呈现常驻微胶囊，单键直达呼出「需要你」中断队列并锚定条目。
 */

import React, { useMemo } from 'react';
import { ShieldAlert, ArrowRight, Bell, Sparkles } from 'lucide-react';
import { useNeedsYouQueueStore } from './useNeedsYouQueueStore';
import { calculateQueueSummary } from './needsYouQueueEngine';

export interface AnchoredAlertNotificationBannerProps {
  className?: string;
}

export const AnchoredAlertNotificationBanner: React.FC<AnchoredAlertNotificationBannerProps> = ({
  className = '',
}) => {
  const items = useNeedsYouQueueStore((s) => s.items);
  const alerts = useNeedsYouQueueStore((s) => s.alerts);
  const openDrawer = useNeedsYouQueueStore((s) => s.openDrawer);

  const summary = useMemo(() => {
    return calculateQueueSummary(items, alerts);
  }, [items, alerts]);

  if (summary.totalPendingCount === 0) {
    return null;
  }

  const latestAlert = alerts.find((a) => !a.isRead) ?? alerts[0];

  return (
    <output
      aria-live="polite"
      className={`inline-flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-background/90 backdrop-blur-md border border-border/80 shadow-md transition-all hover:border-primary/50 text-xs ${className}`}
      data-testid="anchored-alert-notification-banner"
    >
      <div className="flex items-center gap-1.5">
        <div
          className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 ${
            summary.urgentCount > 0
              ? 'bg-red-500/15 text-destructive animate-pulse'
              : 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
          }`}
        >
          {summary.urgentCount > 0 ? (
            <ShieldAlert className="w-3 h-3" />
          ) : (
            <Bell className="w-3 h-3" />
          )}
        </div>

        <span className="font-medium text-foreground">
          {summary.totalPendingCount} 项任务需要你
        </span>

        {summary.urgentCount > 0 && (
          <span className="px-1.5 py-0.2 rounded-full bg-red-500/15 text-destructive font-mono text-[10px] font-semibold">
            {summary.urgentCount} 紧急
          </span>
        )}
      </div>

      {latestAlert && (
        <span className="hidden sm:inline-block max-w-[160px] truncate text-[11px] text-muted-foreground border-l border-border/60 pl-2">
          {latestAlert.title}
        </span>
      )}

      <button
        type="button"
        onClick={() => openDrawer(latestAlert?.itemId)}
        className="ml-0.5 text-primary hover:text-primary/80 font-medium flex items-center gap-0.5 transition-colors focus:outline-none"
        data-testid="open-needs-you-drawer-btn"
      >
        <span>接手处理</span>
        <ArrowRight className="w-3 h-3" />
      </button>
    </output>
  );
};
