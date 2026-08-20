'use client';

/**
 * [INPUT]
 * @/services/wikiService::CompileRunStatus (POS: Wiki REST compile_run DTO)
 * next-intl::useTranslations (POS: settings.wiki.queue compilePhase strings)
 *
 * [OUTPUT]
 * WikiCompilePhaseBar: Shared compile phase progress strip for Queue and Overview tabs
 *
 * [POS]
 * Settings Wiki compile visibility. Renders SSE compile_run phase with facet/fast-path hints.
 */

import { useTranslations } from 'next-intl';
import type { CompileRunStatus } from '@/services/wikiService';

const COMPILE_PHASE_STEPS: NonNullable<CompileRunStatus['phase']>[] = [
  'structure_survey',
  'semantic_compile',
  'postprocess',
];

function compilePhaseLabel(
  phase: CompileRunStatus['phase'] | undefined,
  t: ReturnType<typeof useTranslations<'settings.wiki.queue'>>,
): string {
  if (!phase || phase === 'idle') {
    return t('compilePhase.idle');
  }
  const labels: Record<NonNullable<CompileRunStatus['phase']>, string> = {
    idle: t('compilePhase.idle'),
    structure_survey: t('compilePhase.structure_survey'),
    semantic_compile: t('compilePhase.semantic_compile'),
    postprocess: t('compilePhase.postprocess'),
  };
  return labels[phase] ?? t('compilePhase.idle');
}

function compilePhaseStepIndex(phase: CompileRunStatus['phase'] | undefined): number {
  if (!phase || phase === 'idle') {
    return -1;
  }
  return COMPILE_PHASE_STEPS.indexOf(phase);
}

export interface WikiCompilePhaseBarProps {
  compileRun: CompileRunStatus;
  pendingCount?: number;
  processingCount?: number;
  forceVisible?: boolean;
}

export function shouldShowWikiCompilePhaseBar(
  compileRun: CompileRunStatus | null | undefined,
  options?: { pendingCount?: number; processingCount?: number; forceVisible?: boolean },
): compileRun is CompileRunStatus {
  if (!compileRun || compileRun.state === 'paused') {
    return false;
  }
  const phase = compileRun.phase;
  if (options?.forceVisible) {
    return phase !== undefined && phase !== 'idle';
  }
  if (phase === undefined || phase === 'idle') {
    return false;
  }
  const pending = options?.pendingCount ?? 0;
  const processing = options?.processingCount ?? 0;
  return pending > 0 || processing > 0 || phase === 'postprocess';
}

export function WikiCompilePhaseBar({
  compileRun,
  pendingCount = 0,
  processingCount = 0,
  forceVisible = false,
}: WikiCompilePhaseBarProps) {
  const t = useTranslations('settings.wiki.queue');
  if (!shouldShowWikiCompilePhaseBar(compileRun, { pendingCount, processingCount, forceVisible })) {
    return null;
  }

  const activeCompilePhase = compileRun.phase;
  const compilePhaseIndex = compilePhaseStepIndex(activeCompilePhase);

  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium text-foreground">
          {t('compilePhase.title', {
            phase: compilePhaseLabel(activeCompilePhase, t),
          })}
        </div>
        {compileRun.survey_skipped ? (
          <span className="text-xs text-muted-foreground">{t('compilePhase.fastPath')}</span>
        ) : compileRun.facet_count !== undefined && compileRun.facet_count > 0 ? (
          <span className="text-xs text-muted-foreground">
            {t('compilePhase.facetSummary', {
              facets: compileRun.facet_count,
              warnings: compileRun.warning_count ?? 0,
            })}
          </span>
        ) : null}
      </div>
      <div className="flex gap-1">
        {COMPILE_PHASE_STEPS.map((step, index) => {
          const isActive = index === compilePhaseIndex;
          const isComplete = compilePhaseIndex > index;
          return (
            <div
              key={step}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                isActive ? 'bg-primary' : isComplete ? 'bg-primary/40' : 'bg-muted-foreground/20'
              }`}
              title={compilePhaseLabel(step, t)}
            />
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        {activeCompilePhase === 'structure_survey' && t('compilePhase.structureSurveyHint')}
        {activeCompilePhase === 'semantic_compile' && t('compilePhase.semanticCompileHint')}
        {activeCompilePhase === 'postprocess' && t('compilePhase.postprocessHint')}
      </p>
    </div>
  );
}
