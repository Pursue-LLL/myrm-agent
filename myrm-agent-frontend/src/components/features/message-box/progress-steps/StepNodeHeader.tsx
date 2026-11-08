/**
 * [INPUT]
 * - ./StepHeading::{StepStatusIcon, StepTitle} (POS: 步骤图标与标题行)
 * - ./stepTone::* (POS: 状态到颜色的映射)
 * - ./utils::{getStepTitle, WARNING_NOTICE} (POS: 步骤标题与警告色)
 *
 * [OUTPUT]
 * - StepNodeHeader: 树节点的头部：图标、标题、错误分类 / 责任方徽标、耗时、详情入口、进度百分比与进度条。
 *
 * [POS]
 * 进度步骤树节点的头部行：纯展示，详情入口通过回调交给上层打开弹窗；以 Fragment 返回头部行与其下的进度条，二者与节点正文同为兄弟节点。
 */

import { Clock, Info } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import type { TranslateFn } from '@/lib/humanize';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';
import { cn } from '@/lib/utils/classnameUtils';
import type { ProgressItem } from '@/store/chat/types';
import { StepStatusIcon, StepTitle } from './StepHeading';
import { progressTextTone, stepTitleTone, type StepVisualState } from './stepTone';
import { WARNING_NOTICE, getStepTitle } from './utils';

interface StepNodeHeaderProps {
  step: ProgressItem;
  state: StepVisualState;
  t: TranslateFn;
  tHumanize: TranslateFn;
  onViewDetail: (step: ProgressItem) => void;
}

const formatDuration = (ms: number): string => (ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);

export function StepNodeHeader({ step, state, t, tHumanize, onViewDetail }: StepNodeHeaderProps) {
  return (
    <>
      <div className="flex items-center gap-2">
        <StepStatusIcon step={step} state={state} />
        <StepTitle
          step={step}
          title={getStepTitle(step, t, true, tHumanize)}
          t={t}
          className={cn(
            'text-sm font-normal transition-colors duration-200',
            stepTitleTone(state, 'text-foreground group-hover:text-foreground/90'),
            step.is_plan && 'font-semibold',
          )}
        />
        {step.error_category && (
          <Badge
            variant={state.isWarning ? 'outline' : 'destructive'}
            className={cn(
              'ml-1 h-4 px-1.5 text-[9px] uppercase tracking-wider font-bold shrink-0',
              state.isWarning && WARNING_NOTICE.badge,
            )}
          >
            {t(`errorCategories.${step.error_category}`)}
          </Badge>
        )}
        {step.fault_side && step.fault_side !== 'unknown' && (
          <span
            className={cn(
              'ml-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide shrink-0',
              state.isWarning
                ? 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30'
                : 'bg-destructive/10 text-destructive-text border border-destructive/25',
            )}
          >
            {t(`faultSides.${step.fault_side}`)}
          </span>
        )}
        {step.duration_ms != null && step.duration_ms > 0 && (
          <span className="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-mono tabular-nums bg-muted/60 text-muted-foreground border border-border/40 flex-shrink-0">
            <Clock className="w-2.5 h-2.5 opacity-70" />
            {formatDuration(step.duration_ms)}
          </span>
        )}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onViewDetail(step);
          }}
          title={t('viewDetailTooltip')}
          className={cn(
            'ml-auto p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-all duration-150 shrink-0',
            REVEAL_ON_HOVER,
          )}
        >
          <Info className="w-3.5 h-3.5" />
        </button>
        {step.progress_percent != null && (
          <span className={`ml-1 text-xs tabular-nums flex-shrink-0 ${progressTextTone(step.notify_level)}`}>
            {step.progress_percent}%
          </span>
        )}
      </div>
      {step.progress_percent != null && (
        <div
          className={`h-1 w-full rounded-full overflow-hidden ${
            step.notify_level === 'alert'
              ? 'bg-destructive/15'
              : step.notify_level === 'warn'
                ? 'bg-amber-500/15 dark:bg-amber-400/15'
                : 'bg-muted/50'
          }`}
        >
          <div
            className={`h-full rounded-full transition-all duration-500 ease-out ${
              step.notify_level === 'alert'
                ? 'bg-destructive'
                : step.notify_level === 'warn'
                  ? 'bg-amber-500 dark:bg-amber-400'
                  : 'bg-primary/70'
            }`}
            style={{ width: `${Math.min(step.progress_percent, 100)}%` }}
          />
        </div>
      )}
    </>
  );
}
