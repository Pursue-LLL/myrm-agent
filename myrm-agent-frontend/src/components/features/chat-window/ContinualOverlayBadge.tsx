'use client';

/**
 * [INPUT]
 * Continual session overlay state and callbacks.
 *
 * [OUTPUT]
 * ContinualOverlayBadge: Floating badge & card displaying active fault-site session overlay status.
 *
 * [POS]
 * Real-time UI indicator showing zero-reset in-flight self-healing status,
 * remaining TTL turns, and human-in-the-loop rollback control.
 */

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Activity, ChevronDown, ChevronUp, RotateCcw, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';

export interface ActiveOverlayItem {
  overlayId: string;
  shellType: 'prompt_patch' | 'skill_variant' | 'subagent_config' | 'procedural_memory';
  triggerReason: string;
  remainingTurns: number;
  advisoryText?: string;
}

interface ContinualOverlayBadgeProps {
  overlays: ActiveOverlayItem[];
  onRollback?: (overlayId: string) => Promise<void>;
  className?: string;
}

export const ContinualOverlayBadge = memo<ContinualOverlayBadgeProps>(
  ({ overlays, onRollback, className }) => {
    const t = useTranslations('continualOverlay');
    const [expanded, setExpanded] = useState(false);
    const [rollingBackId, setRollingBackId] = useState<string | null>(null);

    const activeList = overlays.filter((o) => o.remainingTurns > 0);

    const handleRollback = useCallback(
      async (id: string) => {
        if (!onRollback || rollingBackId) return;
        setRollingBackId(id);
        try {
          await onRollback(id);
        } finally {
          setRollingBackId(null);
        }
      },
      [onRollback, rollingBackId]
    );

    if (activeList.length === 0) {
      return null;
    }

    const firstOverlay = activeList[0];

    return (
      <div
        className={cn(
          'w-full max-w-2xl mx-auto my-2 rounded-xl border border-violet-500/20 bg-gradient-to-r from-violet-500/5 via-background to-violet-500/5 p-3 shadow-xs transition-all duration-200',
          className
        )}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600 dark:text-violet-400">
              <Activity className="h-4 w-4 animate-pulse" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold text-foreground">
                  {t('activeTitle')}
                </span>
                <span className="inline-flex items-center rounded-md border border-violet-500/30 bg-violet-500/10 px-1.5 py-0.5 text-[10px] font-medium text-violet-700 dark:text-violet-300">
                  {t('remainingTurns', { count: firstOverlay.remainingTurns })}
                </span>
              </div>
              <p className="truncate text-xs text-muted-foreground mt-0.5">
                {firstOverlay.advisoryText || firstOverlay.triggerReason}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {onRollback && (
              <Button
                size="sm"
                variant="ghost"
                disabled={Boolean(rollingBackId)}
                onClick={() => handleRollback(firstOverlay.overlayId)}
                className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                title={t('rollbackTooltip')}
              >
                <RotateCcw className="h-3.5 w-3.5 mr-1" />
                <span className="hidden sm:inline">{t('rollback')}</span>
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setExpanded((prev) => !prev)}
              className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
              aria-label={expanded ? t('collapse') : t('expand')}
            >
              {expanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        {expanded && (
          <div className="mt-3 space-y-2 border-t border-border/50 pt-2.5 text-xs">
            <div className="flex items-center gap-1.5 text-muted-foreground font-medium">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
              <span>{t('howItWorks')}</span>
            </div>
            <p className="text-muted-foreground leading-relaxed pl-5">
              {t('howItWorksDesc')}
            </p>

            {activeList.length > 1 && (
              <div className="space-y-1.5 pt-1.5">
                <span className="text-[11px] font-medium text-foreground">
                  {t('allActiveOverlays', { count: activeList.length })}
                </span>
                {activeList.map((item) => (
                  <div
                    key={item.overlayId}
                    className="flex items-center justify-between rounded-md bg-muted/40 px-2.5 py-1.5"
                  >
                    <span className="truncate pr-2 text-muted-foreground">
                      [{item.shellType}] {item.advisoryText || item.triggerReason}
                    </span>
                    <span className="shrink-0 text-[10px] text-muted-foreground">
                      {t('remainingTurns', { count: item.remainingTurns })}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }
);

ContinualOverlayBadge.displayName = 'ContinualOverlayBadge';
