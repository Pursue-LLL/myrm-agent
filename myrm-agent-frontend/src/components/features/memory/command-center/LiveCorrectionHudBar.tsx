/**
 * [INPUT]
 * @/services/memory::LiveCorrectionStatusResponse
 * Lucide icons (Activity, RefreshCw, Database, Layers)
 *
 * [OUTPUT]
 * Component: LiveCorrectionHudBar
 *
 * [POS]
 * Operational HUD status header for Item 128 Live Correction Studio.
 * Strictly typed, zero any, a11y compliant with visible focus rings. Single file < 200 lines.
 */

'use client';

import React from 'react';
import { Activity, Database, Layers, RefreshCw } from 'lucide-react';
import type { LiveCorrectionStatusResponse } from '@/services/memory';

interface LiveCorrectionHudBarProps {
  status: LiveCorrectionStatusResponse | null;
  isLoading: boolean;
  onReset: () => void;
  isResetting: boolean;
}

export const LiveCorrectionHudBar: React.FC<LiveCorrectionHudBarProps> = ({
  status,
  isLoading,
  onReset,
  isResetting,
}) => {
  const isHealthy = status?.service_status === 'ready' || status?.service_status === 'reset_completed';

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border/60 bg-muted/20 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-6">
        {/* Engine status indicator */}
        <div className="flex items-center gap-2">
          <Activity
            className={`h-4 w-4 ${isHealthy ? 'text-emerald-500' : 'text-amber-500'} ${
              isLoading ? 'animate-pulse' : ''
            }`}
            aria-hidden="true"
          />
          <span className="font-medium text-foreground">实时记忆重校引擎</span>
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
              isHealthy
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
            }`}
          >
            {isLoading
              ? '加载中...'
              : status?.service_status === 'ready' || status?.service_status === 'reset_completed'
                ? '准备就绪'
                : status?.service_status || '准备就绪'}
          </span>
        </div>

        {/* Candidate pool count */}
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Database className="h-4 w-4 text-primary/70" aria-hidden="true" />
          <span>活跃候选记忆:</span>
          <span className="font-semibold text-foreground">
            {status?.candidates_count ?? 0}
          </span>
        </div>

        {/* Executed mutations count */}
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Layers className="h-4 w-4 text-primary/70" aria-hidden="true" />
          <span>已生效纠错数:</span>
          <span className="font-semibold text-foreground">
            {status?.mutations_count ?? 0}
          </span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onReset}
          disabled={isResetting || isLoading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground shadow-sm transition hover:bg-muted focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 disabled:pointer-events-none disabled:opacity-50"
          aria-label="重置测试候选池与纠错历史"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isResetting ? 'animate-spin' : ''}`}
            aria-hidden="true"
          />
          <span>重置测试池</span>
        </button>
      </div>
    </div>
  );
};
