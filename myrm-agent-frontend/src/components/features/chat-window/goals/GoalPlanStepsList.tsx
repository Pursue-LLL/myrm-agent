'use client';

import { useTranslations } from 'next-intl';
import { ListTodo, Loader2, CheckCircle2, Circle, XCircle } from 'lucide-react';
import type { PlanStep } from '@/store/chat/goals/usePlanStore';
import { cn } from '@/lib/utils/classnameUtils';

interface GoalPlanStepsListProps {
  goal: string;
  steps: PlanStep[];
  compact?: boolean;
}

function StepStatusIcon({ status }: { status: PlanStep['status'] }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-4 w-4 text-emerald-500 dark:text-emerald-400" />;
    case 'in_progress':
      return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
    case 'skipped':
      return <XCircle className="h-4 w-4 text-muted-foreground" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground/50" />;
  }
}

export function GoalPlanStepsList({ goal, steps, compact = false }: GoalPlanStepsListProps) {
  const t = useTranslations('Goal');

  return (
    <div className={cn('space-y-3', compact ? 'p-0' : 'p-4')}>
      <div className={cn('flex items-start gap-2', compact && 'px-1')}>
        <ListTodo className="h-4 w-4 shrink-0 text-primary mt-0.5" />
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('goalPlan')}</p>
          <p className={cn('font-medium text-foreground', compact ? 'text-sm' : 'text-base')}>{goal}</p>
        </div>
      </div>
      <ul className="space-y-2">
        {steps.map((step, index) => (
          <li
            key={step.step_id}
            className={cn(
              'flex gap-3 rounded-2xl border p-3 transition-colors',
              step.status === 'in_progress' && 'border-primary/30 bg-primary/5',
              step.status === 'completed' && 'border-border/60 bg-muted/20',
              step.status !== 'in_progress' && step.status !== 'completed' && 'border-border bg-card',
            )}
          >
            <StepStatusIcon status={step.status} />
            <p
              className={cn(
                'flex-1 text-sm leading-snug',
                step.status === 'completed' ? 'text-muted-foreground line-through' : 'text-foreground',
              )}
            >
              {index + 1}. {step.description}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
