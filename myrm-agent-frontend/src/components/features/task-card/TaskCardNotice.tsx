/**
 * [INPUT]
 * @/lib/utils::cn (POS: Class name merger)
 *
 * [OUTPUT]
 * TaskCardNotice: Neutral one-paragraph card for a task state that has no result to show.
 *
 * [POS]
 * Shared shell of the cancelled, expired and result-unavailable states, so the three task surfaces
 * read the same instead of each drawing its own box.
 */

import React from 'react';
import { cn } from '@/lib/utils';

interface TaskCardNoticeProps {
  children: React.ReactNode;
  className?: string;
}

export const TaskCardNotice: React.FC<TaskCardNoticeProps> = ({ children, className }) => (
  <div className={cn('rounded-lg border border-border/50 bg-muted/20 p-4', className)}>
    <p className="text-sm text-muted-foreground">{children}</p>
  </div>
);

export default TaskCardNotice;
