/**
 * [INPUT]
 * ./useTrajectoryDiff::LoadState (POS: what has been read for this side)
 * ./trajectoryDiffModel::turnStartIndexes (POS: turn offsets among all steps)
 *
 * [OUTPUT]
 * TrajectoryColumn: one session's trajectory as a column of turns and tool-call cards, the diverging step marked
 *
 * [POS]
 * One side of TrajectoryDiffModal.
 */

'use client';

import { Layers, Wrench } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/utils/classnameUtils';
import type { SessionTrajectoryResponse, TrajectoryStep } from '@/services/chat';

import { turnStartIndexes } from './trajectoryDiffModel';
import type { LoadState } from './useTrajectoryDiff';

function StepCard({ step, divergent }: { step: TrajectoryStep; divergent: boolean }) {
  const t = useTranslations('trajectoryDiff');

  return (
    <div
      data-divergent={divergent || undefined}
      className={cn(
        'p-2.5 rounded-lg border text-xs space-y-1.5 transition-colors',
        divergent
          ? 'border-amber-500 bg-amber-500/10'
          : step.is_error
            ? 'border-destructive/50 bg-destructive/5'
            : 'border-border/80 bg-card',
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 font-medium">
          <Wrench className="w-3.5 h-3.5 text-primary" />
          <span className="font-mono text-[11px]">{step.tool_name}</span>
          <span className="text-[10px] text-muted-foreground">#{step.step_index}</span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
          <span>{step.duration_ms.toFixed(0)}ms</span>
          {step.tokens_used > 0 && <span>{t('tokensShort', { count: step.tokens_used })}</span>}
        </div>
      </div>
      <pre className="text-[10px] font-mono p-1.5 rounded bg-muted/40 overflow-x-auto text-muted-foreground max-h-20">
        {JSON.stringify(step.tool_args, null, 2)}
      </pre>
    </div>
  );
}

function Turns({
  trajectory,
  divergenceIndex,
}: {
  trajectory: SessionTrajectoryResponse;
  divergenceIndex: number | null;
}) {
  const t = useTranslations('trajectoryDiff');
  const starts = turnStartIndexes(trajectory.turns);

  return trajectory.turns.map((turn, turnIdx) => (
    <div key={turn.turn_id || turnIdx} className="space-y-2">
      <div className="text-[11px] font-medium text-primary bg-primary/5 p-1.5 rounded border border-primary/20 truncate">
        {t('prompt', { text: turn.user_prompt })}
      </div>
      {turn.steps.map((step, stepIdx) => (
        <StepCard key={stepIdx} step={step} divergent={starts[turnIdx] + stepIdx === divergenceIndex} />
      ))}
    </div>
  ));
}

interface TrajectoryColumnProps {
  heading: string;
  state: LoadState<SessionTrajectoryResponse>;
  /** Position among all steps of the session that differs from the other side. */
  divergenceIndex: number | null;
  /** Shown while no session is chosen for this side. */
  placeholder?: string;
  className?: string;
}

export function TrajectoryColumn({ heading, state, divergenceIndex, placeholder, className }: TrajectoryColumnProps) {
  const t = useTranslations('trajectoryDiff');

  return (
    <div className={cn('space-y-4', className)}>
      <div className="flex items-center justify-between font-semibold text-xs text-foreground bg-muted/40 p-2 rounded">
        <span>{heading}</span>
        {state.status === 'ready' && (
          <span className="font-mono text-muted-foreground">
            {t('summary', {
              calls: state.data.total_tool_calls,
              tokens: state.data.total_tokens.toLocaleString(),
            })}
          </span>
        )}
      </div>

      {state.status === 'idle' && placeholder && (
        <div className="flex flex-col items-center justify-center h-48 text-muted-foreground text-xs gap-2">
          <Layers className="w-8 h-8 opacity-20" />
          <span>{placeholder}</span>
        </div>
      )}
      {state.status === 'loading' && (
        <output className="block py-6 text-center text-xs text-muted-foreground">{t('loading')}</output>
      )}
      {state.status === 'error' && (
        <p role="alert" className="py-6 text-center text-xs text-destructive-text">
          {t('loadFailed')}
        </p>
      )}
      {state.status === 'ready' && <Turns trajectory={state.data} divergenceIndex={divergenceIndex} />}
    </div>
  );
}
