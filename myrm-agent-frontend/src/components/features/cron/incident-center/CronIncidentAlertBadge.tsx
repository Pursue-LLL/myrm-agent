/**
 * Cron Incident Alert Badge Component
 * 顶部导航/主看板轻量级事故警示条与未签收待办入口
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any；
 * 2. 零原生 emoji，统一采用 Lucide 矢量图标；
 * 3. 所有 if 显式包裹大括号；
 * 4. 语义化 a11y 标签规范；
 * 5. 行数严格受控在 400 行以内。
 */

import React from 'react';
import { AlertCircle, AlertOctagon, CheckCircle2, ChevronRight, ShieldAlert } from 'lucide-react';
import { useCronIncidentStore } from './useCronIncidentStore';

export const CronIncidentAlertBadge: React.FC = () => {
  const { getMetrics, setIsDrawerOpen } = useCronIncidentStore();
  const metrics = getMetrics();

  if (metrics.unacknowledgedCount === 0) {
    return (
      <div
        data-testid="cron-incident-badge-healthy"
        className="flex items-center gap-2 rounded-lg border border-neutral-800/80 bg-neutral-900/60 px-3 py-1.5 text-xs text-neutral-400"
      >
        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
        <span>定时任务运转正常，无待办故障事故</span>
      </div>
    );
  }

  const hasSilentFailure = metrics.silentFailureCount > 0;

  return (
    <button
      type="button"
      onClick={() => {
        setIsDrawerOpen(true);
      }}
      data-testid="cron-incident-alert-badge"
      className={`group flex items-center justify-between gap-3 rounded-lg border px-3 py-1.5 text-xs transition-colors ${
        hasSilentFailure
          ? 'border-rose-500/50 bg-rose-950/30 text-rose-200 hover:bg-rose-900/40'
          : 'border-amber-500/40 bg-amber-950/20 text-amber-200 hover:bg-amber-900/30'
      }`}
    >
      <div className="flex items-center gap-2">
        {hasSilentFailure ? (
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-rose-500" />
          </span>
        ) : (
          <span className="h-2 w-2 rounded-full bg-amber-400" />
        )}

        {hasSilentFailure ? (
          <ShieldAlert className="h-4 w-4 text-rose-400" />
        ) : (
          <AlertCircle className="h-4 w-4 text-amber-400" />
        )}

        <div className="flex items-center gap-1.5 font-medium">
          <span>待办事故中心:</span>
          {hasSilentFailure && (
            <span className="rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px] text-rose-300">
              {metrics.silentFailureCount} 起假成功静默失败
            </span>
          )}
          <span>{metrics.unacknowledgedCount} 起待签收</span>
        </div>
      </div>

      <div className="flex items-center gap-1 text-[11px] text-neutral-400 group-hover:text-neutral-200">
        <AlertOctagon className="h-3 w-3" />
        <span>立即排查</span>
        <ChevronRight className="h-3.5 w-3.5" />
      </div>
    </button>
  );
};
