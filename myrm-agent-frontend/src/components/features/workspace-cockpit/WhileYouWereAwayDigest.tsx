'use client';

/**
 * [INPUT]
 * ./workspaceCockpitTypes (POS: OfflineDigestSummary, OfflineDigestHighlight)
 * ./useWorkspaceOfflineDigest (POS: formatTimeDuration)
 * @/lib/utils/classnameUtils (POS: cn helper)
 * lucide-react (POS: Clock, CheckCircle2, AlertTriangle, ShieldAlert, Sparkles, X, ChevronRight, Activity)
 *
 * [OUTPUT]
 * WhileYouWereAwayDigest: Prominent banner summarizing offline achievements, failures, and blocked decisions.
 *
 * [POS]
 * "While You Were Away" offline catch-up digest card for Personal Workspace Cockpit. Aligns with LoopX dashboard.
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  Clock,
  CheckCircle2,
  AlertTriangle,
  ShieldAlert,
  Sparkles,
  X,
  ChevronRight,
  Activity,
} from 'lucide-react';
import type { OfflineDigestSummary } from './workspaceCockpitTypes';
import { formatTimeDuration } from './useWorkspaceOfflineDigest';

interface WhileYouWereAwayDigestProps {
  summary: OfflineDigestSummary;
  onDismiss: () => void;
  onNavigateToTask: (chatId: string, taskId?: string) => void;
  className?: string;
}

export const WhileYouWereAwayDigest: React.FC<WhileYouWereAwayDigestProps> = ({
  summary,
  onDismiss,
  onNavigateToTask,
  className,
}) => {
  const awayFormatted = formatTimeDuration(summary.awayDurationMs);

  return (
    <section
      data-testid="while-you-were-away-digest"
      aria-label="Offline activity digest"
      className={cn(
        'relative overflow-hidden rounded-xl border border-primary/20 bg-gradient-to-r from-primary/10 via-background to-accent-warm/10 p-4 shadow-sm',
        className,
      )}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-border/50">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-primary/20 text-primary">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
              While You Were Away
              <span className="text-xs font-normal text-muted-foreground flex items-center gap-1">
                <Clock className="w-3 h-3" />
                ({awayFormatted})
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">
              Here is what your digital team achieved and what requires your input.
            </p>
          </div>
        </div>

        <button
          type="button"
          data-testid="digest-dismiss-btn"
          onClick={onDismiss}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          aria-label="Dismiss offline digest"
          title="Dismiss"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 4 Metrics Metric Cards Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-3">
        {/* Pending Decisions (High priority) */}
        <div
          data-testid="digest-metric-decisions"
          className={cn(
            'flex flex-col p-2.5 rounded-lg border transition-all',
            summary.pendingDecisionsCount > 0
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400'
              : 'border-border/40 bg-muted/20 text-muted-foreground',
          )}
        >
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="font-medium flex items-center gap-1">
              <ShieldAlert className="w-3.5 h-3.5" />
              Needs You
            </span>
            <span className="text-base font-bold">{summary.pendingDecisionsCount}</span>
          </div>
          <span className="text-[11px] opacity-80">Waiting for approval</span>
        </div>

        {/* In-Progress tasks */}
        <div
          data-testid="digest-metric-in-progress"
          className="flex flex-col p-2.5 rounded-lg border border-border/40 bg-muted/20 text-foreground"
        >
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="font-medium flex items-center gap-1 text-primary">
              <Activity className="w-3.5 h-3.5" />
              Running
            </span>
            <span className="text-base font-bold">{summary.inProgressCount}</span>
          </div>
          <span className="text-[11px] text-muted-foreground">Active in background</span>
        </div>

        {/* Completed Goals */}
        <div
          data-testid="digest-metric-completed"
          className="flex flex-col p-2.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
        >
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="font-medium flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Completed
            </span>
            <span className="text-base font-bold">{summary.completedGoalsCount}</span>
          </div>
          <span className="text-[11px] opacity-80">Goals finalized</span>
        </div>

        {/* Failed Tasks */}
        <div
          data-testid="digest-metric-failed"
          className={cn(
            'flex flex-col p-2.5 rounded-lg border transition-all',
            summary.failedTasksCount > 0
              ? 'border-destructive/40 bg-destructive/10 text-destructive'
              : 'border-border/40 bg-muted/20 text-muted-foreground',
          )}
        >
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="font-medium flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" />
              Failed
            </span>
            <span className="text-base font-bold">{summary.failedTasksCount}</span>
          </div>
          <span className="text-[11px] opacity-80">Need inspection</span>
        </div>
      </div>

      {/* Highlights List */}
      {summary.highlights.length > 0 && (
        <div className="space-y-1.5 pt-1">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            Key Changes & Action Items
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {summary.highlights.slice(0, 4).map((h) => (
              <button
                key={h.id}
                type="button"
                onClick={() => onNavigateToTask(h.chatId, h.id)}
                className="flex items-center justify-between p-2 rounded-md bg-background/80 hover:bg-background border border-border/60 text-xs text-left transition-colors group"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {h.type === 'decision' && <ShieldAlert className="w-3.5 h-3.5 shrink-0 text-amber-500" />}
                  {h.type === 'failure' && <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-destructive" />}
                  {h.type === 'success' && <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-500" />}
                  <span className="truncate text-foreground font-medium">{h.title}</span>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground shrink-0 ml-2">
                  <span>{h.timeAgo} ago</span>
                  <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};

export default React.memo(WhileYouWereAwayDigest);
