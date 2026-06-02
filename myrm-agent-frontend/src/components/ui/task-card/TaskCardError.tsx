/**
 * Error UI for failed tasks with retry button.
 */

import React from 'react';
import { AlertCircle, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import type { TaskError } from '@/store/tasks/types';

interface TaskCardErrorProps {
  error: TaskError;
  onRetry?: () => void;
  className?: string;
}

export const TaskCardError: React.FC<TaskCardErrorProps> = ({ error, onRetry, className }) => {
  return (
    <div className={cn('rounded-lg border border-destructive/50 bg-destructive/5 p-4 space-y-3', className)}>
      {/* Error icon */}
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-destructive mt-0.5" />
        <div className="flex-1 space-y-1">
          <p className="text-sm font-medium text-foreground">Task Failed</p>
          <p className="text-sm text-foreground/70">{error.message}</p>
        </div>
      </div>

      {/* Retry button (only for transient errors) */}
      {error.recoverable === 'transient' && onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="w-full">
          <RotateCcw className="w-4 h-4 mr-2" />
          Retry Task
        </Button>
      )}
    </div>
  );
};

export default TaskCardError;
