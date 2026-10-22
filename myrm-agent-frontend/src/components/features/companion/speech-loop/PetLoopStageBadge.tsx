import React from 'react';
import {
  Compass,
  Code2,
  Cpu,
  CheckCircle2,
  Loader2,
  Clock,
  AlertCircle,
} from 'lucide-react';
import { FourStagePhase, LoopTaskStep } from './petSpeechLoopTypes';

export interface PetLoopStageBadgeProps {
  steps: LoopTaskStep[];
  className?: string;
}

export const PetLoopStageBadge: React.FC<PetLoopStageBadgeProps> = ({
  steps,
  className = '',
}) => {
  if (steps.length === 0) {
    return null;
  }

  const stageIcons: Record<
    FourStagePhase,
    React.ComponentType<{ className?: string }>
  > = {
    plan: Compass,
    code: Code2,
    exec: Cpu,
    verify: CheckCircle2,
  };

  const stageLabels: Record<FourStagePhase, string> = {
    plan: '规划',
    code: '编码',
    exec: '执行',
    verify: '自检',
  };

  return (
    <div
      data-testid="pet-loop-stage-badge"
      className={`flex items-center gap-1.5 p-1.5 px-2.5 rounded-full bg-zinc-950/90 border border-zinc-800 backdrop-blur-md shadow-lg font-mono text-[11px] ${className}`}
    >
      {steps.map((step, idx) => {
        const Icon = stageIcons[step.stage];
        const isRunning = step.status === 'running';
        const isCompleted = step.status === 'completed';
        const isFailed = step.status === 'failed';

        let badgeStyle = 'text-zinc-500 border-zinc-800 bg-zinc-900/40';
        if (isRunning) {
          badgeStyle =
            'text-indigo-300 border-indigo-500/50 bg-indigo-500/20 animate-pulse';
        } else if (isCompleted) {
          badgeStyle = 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10';
        } else if (isFailed) {
          badgeStyle = 'text-rose-400 border-rose-500/40 bg-rose-500/10';
        }

        return (
          <React.Fragment key={step.id}>
            <div
              className={`flex items-center gap-1 px-2 py-0.5 rounded-full border transition-all ${badgeStyle}`}
              title={`${stageLabels[step.stage]}: ${step.title} (${step.status})`}
            >
              {isRunning ? (
                <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
              ) : isCompleted ? (
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              ) : isFailed ? (
                <AlertCircle className="w-3 h-3 text-rose-400" />
              ) : (
                <Icon className="w-3 h-3" />
              )}
              <span className="font-semibold">{stageLabels[step.stage]}</span>
              {step.durationMs !== undefined && (
                <span className="text-[9px] text-zinc-400 opacity-80">
                  {step.durationMs}ms
                </span>
              )}
            </div>

            {idx < steps.length - 1 && (
              <span className="text-zinc-600 text-[10px]">→</span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};
