/**
 * Placeholder UI for pending/running tasks.
 * Shows skeleton loader with progress bar.
 */

import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/primitives/progress';

interface TaskCardPlaceholderProps {
  prompt?: string;
  progress?: number;
  className?: string;
}

export const TaskCardPlaceholder: React.FC<TaskCardPlaceholderProps> = ({ prompt, progress = 0, className }) => {
  return (
    <div className={cn('rounded-lg border border-border/50 bg-card p-4 space-y-3', className)}>
      {/* Skeleton image */}
      <div className="relative w-full aspect-square bg-muted/30 rounded-md flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>

      {/* Progress bar */}
      {progress > 0 && <Progress value={progress * 100} className="h-1" />}

      {/* Prompt */}
      {prompt && <p className="text-sm text-foreground/70 line-clamp-2">{prompt}</p>}

      {/* Status text */}
      <p className="text-xs text-muted-foreground">
        {progress > 0 ? `Generating... ${Math.round(progress * 100)}%` : 'Queued...'}
      </p>
    </div>
  );
};

export default TaskCardPlaceholder;
