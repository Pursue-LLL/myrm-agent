/**
 * Placeholder UI for pending/running tasks.
 * Shows skeleton loader with progress bar.
 */

import React from 'react';
import { Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/primitives/progress';

interface TaskCardPlaceholderProps {
  taskId?: string;
  prompt?: string;
  progress?: number;
  statusMessage?: string;
  onCancel?: (taskId: string) => void;
  className?: string;
}

export const TaskCardPlaceholder: React.FC<TaskCardPlaceholderProps> = ({
  taskId,
  prompt,
  progress = 0,
  statusMessage,
  onCancel,
  className,
}) => {
  const t = useTranslations('taskCard');
  const [isCancelling, setIsCancelling] = React.useState(false);

  const handleCancel = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!taskId || !onCancel || isCancelling) return;
    setIsCancelling(true);
    try {
      await onCancel(taskId);
    } catch {
      // 网络或服务端异常时优雅恢复，避免未捕获异常中断组件渲染
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <div className={cn('rounded-lg border border-border/50 bg-card p-4 space-y-3 relative group', className)}>
      <div className="relative w-full aspect-square bg-muted/30 rounded-md flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>

      {progress > 0 && <Progress value={progress * 100} className="h-1" />}

      {prompt && <p className="text-sm text-foreground/70 line-clamp-2">{prompt}</p>}

      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground truncate">
          {statusMessage ||
            (progress > 0 ? t('generatingProgress', { percent: Math.round(progress * 100) }) : t('queued'))}
        </p>

        {taskId && onCancel && (
          <button
            type="button"
            disabled={isCancelling}
            onClick={handleCancel}
            aria-label={t('cancelTask')}
            className={cn(
              'shrink-0 text-xs px-2 py-0.5 rounded border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50'
            )}
          >
            {isCancelling ? t('cancelling') : t('cancelTask')}
          </button>
        )}
      </div>

      <p className="text-xs text-muted-foreground/80">{t('backgroundHint')}</p>
    </div>
  );
};

export default TaskCardPlaceholder;
