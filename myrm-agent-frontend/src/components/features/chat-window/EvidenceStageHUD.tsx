'use client';

/**
 * [INPUT]
 * - @/store/chat/types::ProgressItem (POS: Progress step with tool/plan execution metadata)
 * - @/components/features/icons/PremiumIcons (POS: Premium status icons)
 * - next-intl::useTranslations (POS: i18n support)
 *
 * [OUTPUT]
 * - EvidenceStageHUD: Visual four-state stage progression bar (Prepared -> Executing -> Observed -> Verified)
 *   with interactive evidence snapshot drawer.
 *
 * [POS]
 * Renders the deterministic "Evidence Before Claims" execution HUD for chat runs.
 * Decouples model claims from verified runtime evidence.
 */

import React, { memo, useState, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { ProgressItem } from '@/store/chat/types/progress';
import {
  IconBrain,
  IconCheckCircle,
  IconChevronDown,
  IconChevronUp,
  IconClock,
  IconLoader,
  IconPlay,
  IconShieldAlert,
  IconWrench,
  IconXCircle,
} from '@/components/features/icons/PremiumIcons';

export type EvidenceStageKey = 'prepared' | 'executing' | 'observed' | 'verified';
export type StageStatus = 'pending' | 'running' | 'success' | 'warning' | 'error' | 'unverified';

interface EvidenceStageSummary {
  key: EvidenceStageKey;
  status: StageStatus;
  label: string;
  detail: string;
  itemCount: number;
  durationMs: number;
}

interface EvidenceStageHUDProps {
  steps?: ProgressItem[];
  loading?: boolean;
  className?: string;
  defaultExpanded?: boolean;
}

const VERIFY_TOOL_REGEX = /(test|pytest|check|verify|lint|typecheck|eval|audit|assertion)/i;

export const EvidenceStageHUD = memo<EvidenceStageHUDProps>(({
  steps = [],
  loading = false,
  className = '',
  defaultExpanded = false,
}) => {
  const t = useTranslations('evidenceStageHUD');
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [selectedStage, setSelectedStage] = useState<EvidenceStageKey | null>(null);

  const toggleExpand = useCallback(() => {
    setExpanded((prev) => !prev);
  }, []);

  const handleStageClick = useCallback((stageKey: EvidenceStageKey) => {
    setExpanded(true);
    setSelectedStage((prev) => (prev === stageKey ? null : stageKey));
  }, []);

  const derivedStages = useMemo(() => {
    if (!steps || steps.length === 0) {
      return null;
    }

    const planSteps = steps.filter((s) => s.is_plan);
    const toolSteps = steps.filter((s) => s.tool_name && !s.is_plan);
    const verifySteps = toolSteps.filter((s) => s.tool_name && VERIFY_TOOL_REGEX.test(s.tool_name));

    const totalDuration = steps.reduce((sum, s) => sum + (s.duration_ms || s.elapsed_ms || 0), 0);
    const hasError = steps.some((s) => s.status === 'error' || s.error);
    const hasWarning = steps.some((s) => s.status === 'warning' || s.fault_side);
    const anyRunning = loading || steps.some((s) => s.status === undefined || s.status === 'complete');

    // 1. Prepared Stage
    const prepStatus: StageStatus = planSteps.length > 0 || steps.length > 0 ? 'success' : 'pending';
    const prepSummary: EvidenceStageSummary = {
      key: 'prepared',
      status: prepStatus,
      label: t('stages.prepared.label'),
      detail: planSteps.length > 0
        ? t('stages.prepared.planDeclared', { count: planSteps.length })
        : t('stages.prepared.ready'),
      itemCount: planSteps.length,
      durationMs: 0,
    };

    // 2. Executing Stage
    let execStatus: StageStatus = 'pending';
    if (loading) {
      execStatus = 'running';
    } else if (toolSteps.length > 0) {
      execStatus = hasError ? 'error' : hasWarning ? 'warning' : 'success';
    } else if (steps.length > 0) {
      execStatus = 'success';
    }
    const execSummary: EvidenceStageSummary = {
      key: 'executing',
      status: execStatus,
      label: t('stages.executing.label'),
      detail: loading
        ? t('stages.executing.running')
        : t('stages.executing.completed', { count: toolSteps.length }),
      itemCount: toolSteps.length,
      durationMs: totalDuration,
    };

    // 3. Observed Stage
    let obsStatus: StageStatus = 'pending';
    const finishedTools = toolSteps.filter((s) => s.status === 'success' || s.stdout || (s.duration_ms ?? 0) > 0);
    if (finishedTools.length > 0) {
      obsStatus = 'success';
    } else if (toolSteps.length > 0 && !loading) {
      obsStatus = hasError ? 'error' : 'warning';
    }
    const obsSummary: EvidenceStageSummary = {
      key: 'observed',
      status: obsStatus,
      label: t('stages.observed.label'),
      detail: finishedTools.length > 0
        ? t('stages.observed.evidenceCaptured', { count: finishedTools.length })
        : t('stages.observed.pending'),
      itemCount: finishedTools.length,
      durationMs: totalDuration,
    };

    // 4. Verified Stage
    let verStatus: StageStatus = 'unverified';
    if (verifySteps.length > 0) {
      const allVerifyPassed = verifySteps.every((s) => s.status === 'success' && !s.error);
      if (loading) {
        verStatus = 'running';
      } else {
        verStatus = allVerifyPassed ? 'success' : 'error';
      }
    }
    const verSummary: EvidenceStageSummary = {
      key: 'verified',
      status: verStatus,
      label: t('stages.verified.label'),
      detail: verifySteps.length > 0
        ? (verStatus === 'success' ? t('stages.verified.passed', { count: verifySteps.length }) : t('stages.verified.failed'))
        : t('stages.verified.unverified'),
      itemCount: verifySteps.length,
      durationMs: verifySteps.reduce((sum, s) => sum + (s.duration_ms || s.elapsed_ms || 0), 0),
    };

    return {
      stages: [prepSummary, execSummary, obsSummary, verSummary],
      toolSteps,
      verifySteps,
      totalDuration,
      hasError,
      hasWarning,
      anyRunning,
    };
  }, [steps, loading, t]);

  if (!derivedStages) {
    return null;
  }

  const renderStatusBadge = (status: StageStatus) => {
    switch (status) {
      case 'running':
        return <IconLoader className="w-3 h-3 text-blue-500 animate-spin shrink-0" />;
      case 'success':
        return <IconCheckCircle className="w-3 h-3 text-emerald-500 dark:text-emerald-400 shrink-0" />;
      case 'warning':
        return <IconShieldAlert className="w-3 h-3 text-amber-500 dark:text-amber-400 shrink-0" />;
      case 'error':
        return <IconXCircle className="w-3 h-3 text-rose-500 dark:text-rose-400 shrink-0" />;
      case 'unverified':
        return <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 shrink-0" />;
      default:
        return <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/30 shrink-0" />;
    }
  };

  const getStagePillClass = (stage: EvidenceStageSummary) => {
    const isSelected = selectedStage === stage.key;
    const base = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all cursor-pointer border';
    
    if (isSelected) {
      return cn(base, 'ring-2 ring-primary/40 border-primary bg-primary/10 text-foreground shadow-sm');
    }

    switch (stage.status) {
      case 'running':
        return cn(base, 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30 animate-pulse');
      case 'success':
        return cn(base, 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20');
      case 'warning':
        return cn(base, 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20 hover:bg-amber-500/20');
      case 'error':
        return cn(base, 'bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/20 hover:bg-rose-500/20');
      case 'unverified':
        return cn(base, 'bg-muted/40 text-muted-foreground border-border/40 hover:bg-muted/60');
      default:
        return cn(base, 'bg-background/60 text-muted-foreground border-border/40 hover:bg-muted/30');
    }
  };

  const filteredEvidenceSteps = selectedStage
    ? derivedStages.toolSteps.filter((s) => {
        if (selectedStage === 'verified') return VERIFY_TOOL_REGEX.test(s.tool_name || '');
        if (selectedStage === 'observed') return (s.stdout || (s.duration_ms ?? 0) > 0 || s.status === 'success');
        if (selectedStage === 'executing') return true;
        return s.is_plan;
      })
    : derivedStages.toolSteps;

  return (
    <div
      data-testid="evidence-stage-hud"
      className={cn(
        'rounded-xl border border-border/50 bg-background/80 dark:bg-muted/10 p-2.5 transition-all text-xs space-y-2 mb-2',
        className
      )}
    >
      {/* 顶部胶囊条 */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap">
          {derivedStages.stages.map((stage) => (
            <button
              key={stage.key}
              type="button"
              data-testid={`evidence-stage-${stage.key}`}
              onClick={() => handleStageClick(stage.key)}
              className={getStagePillClass(stage)}
              title={`${stage.label}: ${stage.detail}`}
            >
              {renderStatusBadge(stage.status)}
              <span>{stage.label}</span>
              {stage.itemCount > 0 && (
                <span className="text-[10px] opacity-70 ml-0.5">({stage.itemCount})</span>
              )}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 text-muted-foreground ml-auto">
          {derivedStages.totalDuration > 0 && (
            <span className="flex items-center gap-1 text-[11px]">
              <IconClock className="w-3 h-3 text-muted-foreground/70" />
              <span>
                {derivedStages.totalDuration >= 1000
                  ? `${(derivedStages.totalDuration / 1000).toFixed(1)}s`
                  : `${derivedStages.totalDuration}ms`}
              </span>
            </span>
          )}

          <button
            type="button"
            data-testid="evidence-hud-toggle"
            onClick={toggleExpand}
            className="p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title={expanded ? t('collapse') : t('expand')}
          >
            {expanded ? <IconChevronUp className="w-3.5 h-3.5" /> : <IconChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* 证据快照抽屉 (Evidence Snapshot Drawer) */}
      {expanded && (
        <div
          data-testid="evidence-snapshot-drawer"
          className="mt-2 pt-2 border-t border-border/40 space-y-2 animate-in fade-in slide-in-from-top-1 duration-150"
        >
          <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
            <span className="font-medium text-foreground">
              {selectedStage
                ? t(`drawer.title_${selectedStage}` as 'drawer.title_observed')
                : t('drawer.allEvidence')}
            </span>
            <span>
              {t('drawer.itemCount', { count: filteredEvidenceSteps.length })}
            </span>
          </div>

          <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
            {filteredEvidenceSteps.length === 0 ? (
              <div className="py-3 text-center text-muted-foreground text-[11px]">
                {t('drawer.empty')}
              </div>
            ) : (
              filteredEvidenceSteps.map((step, idx) => (
                <div
                  key={`${step.tool_call_id || step.step_key || idx}`}
                  data-testid="evidence-step-card"
                  className="rounded-lg border border-border/40 bg-muted/20 p-2 text-[11px] space-y-1"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 font-medium text-foreground truncate">
                      <IconWrench className="w-3 h-3 text-primary/70 shrink-0" />
                      <span className="truncate">{step.tool_name || step.step_key}</span>
                      {step.fault_side && (
                        <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 font-mono">
                          {step.fault_side}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0 text-muted-foreground text-[10px]">
                      {(step.duration_ms ?? step.elapsed_ms ?? 0) > 0 && (
                        <span>{step.duration_ms ?? step.elapsed_ms}ms</span>
                      )}
                      <span
                        className={cn(
                          'px-1.5 py-0.2 rounded font-medium',
                          step.status === 'success'
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                            : step.status === 'error'
                            ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                            : 'bg-muted text-muted-foreground'
                        )}
                      >
                        {step.status || (loading ? 'running' : 'done')}
                      </span>
                    </div>
                  </div>

                  {step.reason && (
                    <p className="text-muted-foreground text-[10px] leading-relaxed line-clamp-2">
                      {step.reason}
                    </p>
                  )}

                  {step.stdout && (
                    <div className="mt-1 font-mono text-[10px] bg-background/80 dark:bg-black/40 border border-border/30 rounded p-1.5 text-foreground/80 overflow-x-auto max-h-20 whitespace-pre-wrap">
                      {step.stdout.slice(0, 300)}
                      {step.stdout.length > 300 && '...'}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
});

EvidenceStageHUD.displayName = 'EvidenceStageHUD';
export default EvidenceStageHUD;
