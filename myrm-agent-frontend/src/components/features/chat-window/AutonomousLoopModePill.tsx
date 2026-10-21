'use client';

import React, { useState } from 'react';
import {
  Play,
  Pause,
  Compass,
  AlertCircle,
  CheckCircle2,
  RotateCcw,
  Footprints,
  ChevronDown,
  ChevronUp,
  X,
  FastForward,
} from 'lucide-react';

export type OrchestrationMode = 'autonomous' | 'supervised' | 'paused' | 'completed';
export type StepStatus = 'pending' | 'running' | 'success' | 'failed' | 'paused';

export interface AutonomousLoopStepData {
  step_index: number;
  action_type: string;
  description: string;
  status: StepStatus;
  timestamp: string;
  metadata?: Record<string, string | number | boolean>;
}

export interface AutonomousLoopStateData {
  session_id: string;
  goal_id: string;
  mode: OrchestrationMode;
  current_step: number;
  max_steps: number;
  is_active: boolean;
  history: AutonomousLoopStepData[];
  pause_reason?: string;
  started_at: string;
  last_advanced_at: string;
}

export interface AutonomousLoopModePillProps {
  chatId: string;
  loopState: AutonomousLoopStateData;
  onSetMode?: (mode: OrchestrationMode) => void;
  onAdvanceStep?: () => void;
  onCompleteLoop?: () => void;
  onDismiss?: () => void;
  className?: string;
}

const MODE_CONFIG: Record<
  OrchestrationMode,
  { label: string; badgeClass: string; icon: React.ReactNode }
> = {
  autonomous: {
    label: 'Autonomous Cruise',
    badgeClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    icon: <Compass className="w-3.5 h-3.5 animate-spin-slow text-emerald-400" />,
  },
  supervised: {
    label: 'Supervised Pacing',
    badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    icon: <Pause className="w-3.5 h-3.5 text-amber-400" />,
  },
  paused: {
    label: 'Watchdog Paused',
    badgeClass: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    icon: <AlertCircle className="w-3.5 h-3.5 text-rose-400" />,
  },
  completed: {
    label: 'Goal Completed',
    badgeClass: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    icon: <CheckCircle2 className="w-3.5 h-3.5 text-blue-400" />,
  },
};

export function AutonomousLoopModePill({
  chatId,
  loopState,
  onSetMode,
  onAdvanceStep,
  onCompleteLoop,
  onDismiss,
  className = '',
}: AutonomousLoopModePillProps) {
  const [showHistory, setShowHistory] = useState(false);
  const cfg = MODE_CONFIG[loopState.mode] || MODE_CONFIG.autonomous;
  const progressPercent = Math.min(
    100,
    Math.round((loopState.current_step / Math.max(1, loopState.max_steps)) * 100),
  );

  return (
    <section
      aria-label={`Autonomous Orchestration Loop for ${loopState.goal_id}`}
      data-testid="autonomous-loop-pill"
      className={`rounded-xl border border-zinc-700/80 bg-zinc-900/95 backdrop-blur-md p-4 shadow-xl transition-all ${className}`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${cfg.badgeClass}`}
          >
            {cfg.icon}
            <span>{cfg.label}</span>
          </span>
          <span className="text-xs text-zinc-400 truncate max-w-[140px]" title={loopState.goal_id}>
            Goal: {loopState.goal_id}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Dismiss autonomous loop card"
              className="p-1 rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Progress & Watchdog stats */}
      <div className="mb-3 space-y-1.5">
        <div className="flex items-center justify-between text-xs text-zinc-300">
          <span className="flex items-center gap-1 font-mono">
            <Footprints className="w-3.5 h-3.5 text-zinc-400" />
            Step {loopState.current_step} / {loopState.max_steps}
          </span>
          <span className="text-zinc-400 font-mono">{progressPercent}%</span>
        </div>

        <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              loopState.mode === 'paused'
                ? 'bg-rose-500'
                : loopState.mode === 'completed'
                  ? 'bg-blue-500'
                  : 'bg-emerald-500'
            }`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Pause reason alert banner */}
      {loopState.mode === 'paused' && loopState.pause_reason && (
        <div
          role="alert"
          className="mb-3 p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300 flex items-start gap-2"
        >
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5 min-w-0">
            <div className="font-semibold">Watchdog Intervention:</div>
            <p className="text-rose-200/90 leading-relaxed break-words">{loopState.pause_reason}</p>
          </div>
        </div>
      )}

      {/* Control Actions toolbar */}
      <div className="flex items-center gap-2 pt-1 border-t border-zinc-800/80">
        {loopState.mode === 'autonomous' ? (
          <button
            type="button"
            onClick={() => onSetMode?.('supervised')}
            aria-label="Switch to supervised pacing"
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition"
          >
            <Pause className="w-3.5 h-3.5 text-amber-400" />
            <span>Supervise</span>
          </button>
        ) : loopState.mode === 'completed' ? (
          <button
            type="button"
            onClick={() => onSetMode?.('autonomous')}
            aria-label="Restart autonomous loop"
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-600/30 hover:bg-blue-600/40 text-blue-200 border border-blue-500/40 transition"
          >
            <RotateCcw className="w-3.5 h-3.5 text-blue-400" />
            <span>Restart</span>
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onSetMode?.('autonomous')}
            aria-label="Resume autonomous cruise"
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-600/30 hover:bg-emerald-600/40 text-emerald-200 border border-emerald-500/40 transition"
          >
            <Play className="w-3.5 h-3.5 text-emerald-400" />
            <span>Resume Auto</span>
          </button>
        )}

        {loopState.mode !== 'completed' && onAdvanceStep && (
          <button
            type="button"
            onClick={onAdvanceStep}
            aria-label="Advance single step"
            className="inline-flex items-center justify-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition"
          >
            <FastForward className="w-3.5 h-3.5 text-zinc-300" />
            <span>Step</span>
          </button>
        )}

        {loopState.mode !== 'completed' && onCompleteLoop && (
          <button
            type="button"
            onClick={onCompleteLoop}
            aria-label="Mark goal complete"
            className="inline-flex items-center justify-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-blue-400" />
            <span>Done</span>
          </button>
        )}

        {loopState.history.length > 0 && (
          <button
            type="button"
            onClick={() => setShowHistory((prev) => !prev)}
            aria-label="Toggle execution history"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition"
          >
            {showHistory ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        )}
      </div>

      {/* Step history audit drop-down */}
      {showHistory && loopState.history.length > 0 && (
        <div
          data-testid="autonomous-loop-history"
          className="mt-3 pt-3 border-t border-zinc-800/80 max-h-48 overflow-y-auto space-y-2 pr-1"
        >
          <div className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
            Step Audit Trail ({loopState.history.length})
          </div>
          <ol className="space-y-1.5 list-none p-0 m-0">
            {loopState.history.map((step) => (
              <li
                key={step.step_index}
                className="text-xs p-2 rounded bg-zinc-800/60 border border-zinc-700/50 flex items-start justify-between gap-2"
              >
                <div className="min-w-0 space-y-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-zinc-400 text-[10px]">#{step.step_index}</span>
                    <span className="font-semibold text-zinc-200">{step.action_type}</span>
                  </div>
                  <p className="text-zinc-400 text-[11px] truncate" title={step.description}>
                    {step.description}
                  </p>
                </div>
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${
                    step.status === 'success'
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : step.status === 'failed'
                        ? 'bg-rose-500/20 text-rose-300'
                        : 'bg-amber-500/20 text-amber-300'
                  }`}
                >
                  {step.status}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
