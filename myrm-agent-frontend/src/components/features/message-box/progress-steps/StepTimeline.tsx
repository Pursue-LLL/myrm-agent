/**
 * [INPUT]
 * - ./stepTone::StepVisualState (POS: 步骤视觉状态)
 *
 * [OUTPUT]
 * - StepStatusDot: 步骤的状态圆点。
 * - StepRail: 步骤之间的竖向连接线，可在其中挂载进行中的流光。
 *
 * [POS]
 * 进度步骤的时间线构件：圆点颜色随步骤状态变化，进行中的圆点旋转；展开树节点与折叠摘要共用圆点。
 */

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type { StepVisualState } from './stepTone';

interface StepStatusDotProps {
  state: StepVisualState;
  className?: string;
}

export function StepStatusDot({ state, className }: StepStatusDotProps) {
  const { isWarning, isBlocked, isError, isCurrent, isCompleted } = state;
  return (
    <div
      className={cn(
        'relative w-[16px] sm:w-[20px] h-[16px] sm:h-[20px] rounded-full bg-background border-2 sm:border-3 transition-all duration-300',
        className,
        isWarning
          ? 'border-amber-500 shadow-lg shadow-amber-500/20'
          : isBlocked
            ? 'border-amber-600/70 dark:border-amber-500/70 shadow-lg shadow-amber-500/15'
            : isError
              ? 'border-destructive shadow-lg shadow-destructive/20'
              : isCurrent
                ? 'border-primary shadow-lg shadow-primary/20 animate-rotate-step'
                : isCompleted
                  ? 'border-primary/70 shadow-lg shadow-primary/15'
                  : 'border-muted-foreground/40 shadow-lg shadow-muted/10',
      )}
    >
      <div
        className={cn(
          'absolute inset-[3px] sm:inset-[4px] rounded-full transition-all duration-300',
          isWarning
            ? 'bg-amber-500'
            : isBlocked
              ? 'bg-amber-600/80 dark:bg-amber-500/80'
              : isError
                ? 'bg-destructive'
                : isCurrent
                  ? 'bg-primary animate-rotate-step'
                  : isCompleted
                    ? 'bg-primary/70'
                    : 'bg-muted-foreground/40',
        )}
      />
    </div>
  );
}

export function StepRail({ children }: { children?: ReactNode }) {
  return (
    <div
      className="absolute left-[7px] sm:left-[9px] w-[2px] sm:w-[2px] bg-gradient-to-b from-primary/15 via-primary/25 to-primary/10 dark:from-primary/20 dark:via-primary/30 dark:to-primary/15 rounded-full"
      style={{
        top: '0.5rem',
        bottom: '0.5rem',
      }}
    >
      {children}
    </div>
  );
}
