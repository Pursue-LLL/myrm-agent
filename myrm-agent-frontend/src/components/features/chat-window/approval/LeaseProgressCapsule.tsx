/**
 * @orphan-ok In-place lease progress HUD and quick extension capsule for desktop control
 *
 * [INPUT]
 * - react::FC
 * - lucide-react::Clock, Plus, AlertTriangle, CheckCircle2
 * - zustand::useDesktopControlApprovalStore
 *
 * [OUTPUT]
 * - LeaseProgressCapsule: in-place lease quota progress indicator and extension action.
 *
 * [POS]
 * Inline HUD capsule showing remaining action budget in execution stream, with
 * one-click lease extension when nearing budget depletion.
 */

import React, { useState } from 'react';
import { Clock, Plus, AlertTriangle, CheckCircle2, Pause } from 'lucide-react';
import { apiRequest } from '@/lib/api';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';

export interface LeaseProgressCapsuleProps {
  onExtend?: (additionalSteps: number) => void;
  onPause?: () => void;
  className?: string;
}

export const LeaseProgressCapsule: React.FC<LeaseProgressCapsuleProps> = ({
  onExtend,
  onPause,
  className = '',
}) => {
  const [isExtending, setIsExtending] = useState(false);
  const [isPausing, setIsPausing] = useState(false);
  const { activeEnvelope, extendEnvelopeLease, setEnvelope } = useDesktopControlApprovalStore();

  if (!activeEnvelope || activeEnvelope.status === 'completed') {
    return null;
  }

  const { usedActions, maxActions, remainingBudget } = activeEnvelope;
  const isNearLimit = remainingBudget <= 3 && remainingBudget > 0;
  const isExhausted = remainingBudget <= 0;
  const canExtend =
    activeEnvelope.canExtend !== false && maxActions < (activeEnvelope.hardLimit ?? 100);

  const handleExtend = (steps = 10) => {
    if (!canExtend || isExtending) return;
    setIsExtending(true);
    extendEnvelopeLease(steps);
    onExtend?.(steps);
    setTimeout(() => setIsExtending(false), 300);
  };

  const handlePause = async () => {
    if (isPausing) return;
    setIsPausing(true);
    try {
      await apiRequest('/webui/desktop/envelope/pause', {
        method: 'POST',
        body: JSON.stringify({ task_id: activeEnvelope.taskId }),
      });
    } catch {
      // Best-effort pause request
    } finally {
      setEnvelope(null);
      onPause?.();
      setIsPausing(false);
    }
  };

  return (
    <div
      data-testid="lease-progress-capsule"
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs shadow-2xs backdrop-blur-sm transition-all ${
        isExhausted
          ? 'border-destructive/40 bg-destructive/10 text-destructive'
          : isNearLimit
            ? 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400'
            : 'border-border/80 bg-muted/60 text-muted-foreground'
      } ${className}`}
    >
      <div className="flex items-center gap-1.5 font-medium">
        {isExhausted ? (
          <AlertTriangle className="h-3.5 w-3.5 text-destructive animate-pulse" />
        ) : isNearLimit ? (
          <Clock className="h-3.5 w-3.5 text-amber-500" />
        ) : (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
        )}
        <span>
          免打扰配额: {usedActions}/{maxActions} 步
        </span>
      </div>

      <div className="flex items-center gap-1">
        {(isNearLimit || isExhausted) && (
          <button
            type="button"
            data-testid="extend-lease-btn"
            disabled={!canExtend || isExtending}
            onClick={() => handleExtend(10)}
            className={`inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-all ${
              !canExtend
                ? 'border-border/40 bg-muted/40 text-muted-foreground/50 cursor-not-allowed'
                : 'border-current/30 bg-background/80 text-foreground hover:bg-background hover:scale-105 active:scale-95'
            }`}
          >
            <Plus className="h-3 w-3" />
            {canExtend ? '+10 步续期' : '已达上限'}
          </button>
        )}
        <button
          type="button"
          data-testid="pause-lease-btn"
          disabled={isPausing}
          onClick={() => void handlePause()}
          className="inline-flex items-center gap-1 rounded-full border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive hover:bg-destructive/20 transition-all hover:scale-105 active:scale-95 disabled:opacity-50"
          title="紧急暂停免打扰包络"
        >
          <Pause className="h-3 w-3" />
          暂停
        </button>
      </div>
    </div>
  );
};

export default LeaseProgressCapsule;
