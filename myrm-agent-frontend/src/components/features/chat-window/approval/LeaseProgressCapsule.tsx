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

import React from 'react';
import { Clock, Plus, AlertTriangle, CheckCircle2 } from 'lucide-react';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';

export interface LeaseProgressCapsuleProps {
  onExtend?: (additionalSteps: number) => void;
  className?: string;
}

export const LeaseProgressCapsule: React.FC<LeaseProgressCapsuleProps> = ({
  onExtend,
  className = '',
}) => {
  const { activeEnvelope, extendEnvelopeLease } = useDesktopControlApprovalStore();

  if (!activeEnvelope || activeEnvelope.status === 'completed') {
    return null;
  }

  const { usedActions, maxActions, remainingBudget, status } = activeEnvelope;
  const isNearLimit = remainingBudget <= 3 && remainingBudget > 0;
  const isExhausted = remainingBudget <= 0;

  const handleExtend = (steps = 10) => {
    extendEnvelopeLease(steps);
    onExtend?.(steps);
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
          配额: {usedActions}/{maxActions} 步
        </span>
      </div>

      {(isNearLimit || isExhausted) && (
        <button
          type="button"
          data-testid="extend-lease-btn"
          onClick={() => handleExtend(10)}
          className="inline-flex items-center gap-0.5 rounded-full border border-current/30 bg-background/80 px-2 py-0.5 text-[11px] font-semibold text-foreground hover:bg-background hover:scale-105 active:scale-95 transition-all"
        >
          <Plus className="h-3 w-3" />
          +10 步续期
        </button>
      )}
    </div>
  );
};

export default LeaseProgressCapsule;
