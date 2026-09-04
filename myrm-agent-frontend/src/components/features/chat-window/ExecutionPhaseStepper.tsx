'use client';

/**
 * [INPUT]
 * - @/store/chat/types/agentStream/part1::PhaseTransitionPayload (POS: Stream phase & lane payload)
 * - next-intl::useTranslations (POS: Dual-language i18n support)
 * - @/components/features/icons/PremiumIcons (POS: Premium status icons)
 *
 * [OUTPUT]
 * - ExecutionPhaseStepper: 3-Phase 6-Lane production execution stepper & live telemetry deck.
 *
 * [POS]
 * Visualizes the 3 macro phases and 6 active lanes of the production agent execution lifecycle (Nodes 1-30).
 */

import React, { memo, useState, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { PhaseTransitionPayload } from '@/store/chat/types/agentStream/part1';
import {
  IconCheckCircle,
  IconChevronDown,
  IconChevronUp,
  IconClock,
  IconLoader,
  IconShieldCheck,
} from '@/components/features/icons/PremiumIcons';

export interface ExecutionPhaseStepperProps {
  currentPhase?: PhaseTransitionPayload;
  phaseExecution?: PhaseTransitionPayload;
  phaseHistory?: PhaseTransitionPayload[];
  isStreaming?: boolean;
  loading?: boolean;
  isApprovalPending?: boolean;
  className?: string;
}

interface PhaseStepConfig {
  index: number;
  key: 'planning' | 'executing' | 'verifying';
}

const PHASES: readonly PhaseStepConfig[] = [
  { index: 1, key: 'planning' },
  { index: 2, key: 'executing' },
  { index: 3, key: 'verifying' },
] as const;

export const ExecutionPhaseStepper = memo<ExecutionPhaseStepperProps>(
  ({
    currentPhase,
    phaseExecution,
    phaseHistory = [],
    isStreaming,
    loading = false,
    isApprovalPending = false,
    className = '',
  }) => {
    const t = useTranslations('executionPhaseStepper');
    const [expanded, setExpanded] = useState<boolean>(false);

    const activePayload = currentPhase ?? phaseExecution;
    const effectiveStreaming = isStreaming !== undefined ? isStreaming : loading;

    const activePhaseIndex = useMemo<number>(() => {
      if (!activePayload) {
        return 1;
      }
      if (activePayload.phase === 'completed') {
        return 4;
      }
      return activePayload.phase_index || 1;
    }, [activePayload]);

    const activeLane = isApprovalPending ? 'user' : activePayload?.active_lane || 'agent';
    const isCompleted = activePayload?.phase === 'completed' || (!effectiveStreaming && activePhaseIndex >= 3);

    const getLaneColor = (lane: string): string => {
      switch (lane) {
        case 'user':
          return 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30';
        case 'llm':
          return 'bg-purple-500/15 text-purple-600 dark:text-purple-400 border-purple-500/30';
        case 'mcp':
          return 'bg-cyan-500/15 text-cyan-600 dark:text-cyan-400 border-cyan-500/30';
        case 'skills':
          return 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border-indigo-500/30';
        case 'sandbox':
          return 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30';
        case 'agent':
        default:
          return 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30';
      }
    };

    if (!activePayload && phaseHistory.length === 0 && !effectiveStreaming) {
      return null;
    }

    return (
      <div
        className={cn(
          'my-2 rounded-xl border border-border/40 bg-card/60 backdrop-blur-sm p-3 text-xs shadow-xs transition-all',
          isCompleted ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-primary/20',
          className,
        )}
      >
        {/* Header: Macro Phase Stepper */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 flex-1 min-w-0">
            {PHASES.map((phase, idx) => {
              const isPast = activePhaseIndex > phase.index;
              const isCurrent = activePhaseIndex === phase.index && !isCompleted;

              return (
                <React.Fragment key={phase.key}>
                  {idx > 0 && (
                    <div
                      className={cn(
                        'h-0.5 flex-1 min-w-3 transition-colors',
                        isPast || isCompleted ? 'bg-emerald-500/70' : 'bg-muted/60',
                      )}
                    />
                  )}
                  <div
                    className={cn(
                      'flex items-center gap-1.5 px-2 py-1 rounded-md font-medium transition-all whitespace-nowrap',
                      isCompleted || isPast
                        ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                        : isCurrent
                          ? 'text-primary bg-primary/10 ring-1 ring-primary/30 font-semibold'
                          : 'text-muted-foreground/70 bg-muted/30',
                    )}
                  >
                    {isCompleted || isPast ? (
                      <IconCheckCircle className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                    ) : isCurrent ? (
                      <IconLoader className="h-3.5 w-3.5 text-primary animate-spin shrink-0" />
                    ) : (
                      <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full text-[10px] bg-muted/60 text-muted-foreground shrink-0">
                        {phase.index}
                      </span>
                    )}
                    <span className="text-[11px] truncate">{t(`phases.${phase.key}.title`)}</span>
                  </div>
                </React.Fragment>
              );
            })}
          </div>

          {/* Right Status / Lane Badge & Toggle */}
          <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
            {isCompleted ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                <IconShieldCheck className="h-3 w-3" />
                {t('badge')}
              </span>
            ) : isApprovalPending ? (
              <div
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border animate-pulse',
                  getLaneColor('user'),
                )}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
                <span>{t('waitingApproval')}</span>
              </div>
            ) : (
              <div
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border animate-pulse',
                  getLaneColor(activeLane),
                )}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
                <span>{t(`lanes.${activeLane}`)}</span>
              </div>
            )}

            {phaseHistory.length > 0 && (
              <button
                type="button"
                onClick={() => setExpanded(!expanded)}
                className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground px-1.5 py-0.5 rounded hover:bg-muted/50 transition-colors cursor-pointer"
                title={expanded ? t('collapseTelemetry') : t('expandTelemetry')}
              >
                {expanded ? (
                  <>
                    <span>{t('collapseTelemetry')}</span>
                    <IconChevronUp className="h-3 w-3" />
                  </>
                ) : (
                  <>
                    <span>{t('expandTelemetry')}</span>
                    <IconChevronDown className="h-3 w-3" />
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Current Active Node Callout */}
        {!isCompleted && activePayload?.node_label && (
          <div className="mt-2 pt-2 border-t border-border/30 flex items-center justify-between text-[11px] text-muted-foreground">
            <div className="flex items-center gap-1.5 truncate">
              <span className="px-1.5 py-0.2 rounded bg-muted/50 text-[10px] font-mono">
                {t('currentNode', { nodeId: activePayload.node_id })}
              </span>
              <span className="text-foreground/90 font-medium truncate">{activePayload.node_label}</span>
            </div>
            {activePayload.duration_ms !== undefined && activePayload.duration_ms > 0 && (
              <span className="flex items-center gap-1 shrink-0 text-[10px]">
                <IconClock className="h-3 w-3" />
                {activePayload.duration_ms}ms
              </span>
            )}
          </div>
        )}

        {/* Expanded Telemetry History Deck */}
        {expanded && phaseHistory.length > 0 && (
          <div className="mt-2.5 pt-2 border-t border-border/40 space-y-1.5 max-h-48 overflow-y-auto pr-1">
            {phaseHistory.map((step, idx) => (
              <div
                key={`${step.node_id}-${idx}`}
                className="flex items-center justify-between gap-2 p-1.5 rounded-md bg-muted/20 hover:bg-muted/40 transition-colors text-[10px]"
              >
                <div className="flex items-center gap-1.5 truncate">
                  <span className="font-mono text-muted-foreground/80 shrink-0">
                    #{step.node_id.toString().padStart(2, '0')}
                  </span>
                  <span
                    className={cn(
                      'px-1.5 py-0.2 rounded-xs border text-[9px] shrink-0 font-medium',
                      getLaneColor(step.active_lane),
                    )}
                  >
                    {t(`lanes.${step.active_lane}`)}
                  </span>
                  <span className="truncate text-foreground/80">{step.node_label}</span>
                </div>
                {step.duration_ms !== undefined && step.duration_ms > 0 && (
                  <span className="shrink-0 text-muted-foreground font-mono">{step.duration_ms}ms</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  },
);

ExecutionPhaseStepper.displayName = 'ExecutionPhaseStepper';
