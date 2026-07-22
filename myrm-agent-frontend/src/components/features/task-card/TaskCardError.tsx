/**
 * [INPUT]
 * next-intl::useTranslations (POS: Locale string resolver for task-card copy)
 * @/components/primitives/button::Button (POS: Shared clickable action primitive)
 * @/store/tasks/types::TaskError (POS: Task error shape from task subscription state)
 *
 * [OUTPUT]
 * TaskCardError: Unified failed-state card with retry affordance and retry-error feedback.
 *
 * [POS]
 * Failure-state UI boundary for task cards. It renders localized failure copy and
 * keeps retry interaction semantics consistent across image/video task surfaces.
 */

import React from 'react';
import { AlertCircle, RotateCcw } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';
import { Button } from '@/components/primitives/button';
import type { TaskError } from '@/store/tasks/types';

interface TaskCardErrorProps {
  error: TaskError;
  onRetry?: () => void | Promise<void>;
  isRetrying?: boolean;
  retryErrorMessage?: string;
  className?: string;
}

export const TaskCardError: React.FC<TaskCardErrorProps> = ({
  error,
  onRetry,
  isRetrying = false,
  retryErrorMessage,
  className,
}) => {
  const t = useTranslations('taskCard');

  return (
    <div className={cn('rounded-lg border border-destructive/50 bg-destructive/5 p-4 space-y-3', className)}>
      {/* Error icon */}
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-destructive mt-0.5" />
        <div className="flex-1 space-y-1">
          <p className="text-sm font-medium text-foreground">{t('failedTitle')}</p>
          <p className="text-sm text-foreground/70">{error.message}</p>
        </div>
      </div>

      {/* Retry button (only for transient errors) */}
      {error.recoverable === 'transient' && onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} disabled={isRetrying} className="w-full">
          <RotateCcw className="w-4 h-4 mr-2" />
          {isRetrying ? t('retrying') : t('retryTask')}
        </Button>
      )}
      {retryErrorMessage ? <p className="text-xs text-destructive">{retryErrorMessage}</p> : null}
    </div>
  );
};

export default TaskCardError;
