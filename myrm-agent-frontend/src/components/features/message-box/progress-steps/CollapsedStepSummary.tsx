/**
 * [INPUT]
 * - ./StepHeading::{StepStatusIcon, StepTitle} (POS: 步骤图标与标题行)
 * - ./StepTimeline::StepStatusDot (POS: 状态圆点)
 * - ./StepOutput::StepTerminal (POS: 终端输出)
 * - ./stepTone::* (POS: 状态到颜色的映射)
 * - ./utils::{inferStageLabel, WARNING_NOTICE} (POS: 宏观阶段标签与警告色)
 *
 * [OUTPUT]
 * - CollapsedStepSummary: 折叠状态下的单行摘要。
 *
 * [POS]
 * 进度面板折叠时的摘要：只展示最新（或最近一次图像分析）步骤的宏观阶段而非具体工具，进行中时附带终端最后一行；
 * 有被 evict 的输出时保留完整输出入口。入场动画 `slide-up` 由父面板声明。
 */

import { ChevronDown } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import type { TranslateFn } from '@/lib/humanize';
import { cn } from '@/lib/utils/classnameUtils';
import type { ProgressItem } from '@/store/chat/types';
import { StepStatusIcon, StepTitle } from './StepHeading';
import { StepTerminal } from './StepOutput';
import { StepStatusDot } from './StepTimeline';
import { getStepVisualState, progressTextTone, stepTitleTone } from './stepTone';
import { WARNING_NOTICE, inferStageLabel } from './utils';

interface CollapsedStepSummaryProps {
  step: ProgressItem;
  /** The latest step that has output evicted to a file, if any. */
  evictedStep: ProgressItem | null;
  loading: boolean;
  t: TranslateFn;
}

const lastStdoutLine = (stdout: string): string | undefined => {
  const lines = stdout.split('\n').filter(Boolean);
  return lines[lines.length - 1]?.trim();
};

export function CollapsedStepSummary({ step, evictedStep, loading, t }: CollapsedStepSummaryProps) {
  const state = getStepVisualState(step, loading);
  const latestLine = loading && step.stdout ? lastStdoutLine(step.stdout) : undefined;

  return (
    <>
      <div className="flex items-center gap-3 slide-up group/collapsed -m-1 p-1">
        <div className="flex-shrink-0 p-1 -m-1">
          <StepStatusDot state={state} className="z-10" />
        </div>

        <StepStatusIcon step={step} state={state} />

        <StepTitle
          step={step}
          // 折叠状态：显示宏观阶段而非具体工具
          title={inferStageLabel(step, t)}
          t={t}
          className={cn(
            'text-sm font-normal transition-colors duration-200 line-clamp-1 flex-1',
            stepTitleTone(state, 'text-foreground'),
          )}
        />

        {step.error_category && (
          <Badge
            variant={state.isWarning ? 'outline' : 'destructive'}
            className={cn(
              'ml-1 h-4 px-1.2 text-[8px] uppercase tracking-wider font-bold shrink-0',
              state.isWarning && WARNING_NOTICE.badge,
            )}
          >
            {t(`errorCategories.${step.error_category}`)}
          </Badge>
        )}

        {step.progress_percent != null && (
          <span className={`flex-shrink-0 text-xs tabular-nums ${progressTextTone(step.notify_level)}`}>
            {step.progress_percent}%
          </span>
        )}

        <div className="flex-shrink-0 opacity-0 group-hover/collapsed:opacity-100 transition-opacity duration-200">
          <ChevronDown size={16} className="text-muted-foreground" />
        </div>
      </div>

      {latestLine && (
        <p className="mt-1.5 ml-7 text-[11px] text-muted-foreground/60 font-mono truncate slide-up">{latestLine}</p>
      )}

      {evictedStep && <StepTerminal step={evictedStep} />}
    </>
  );
}
