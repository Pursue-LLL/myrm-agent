'use client';

/**
 * [INPUT]
 * - @/services/mediaTasks::{getMediaTaskChatId,getMediaTaskPrompt} (POS: media task payload helpers)
 *
 * [OUTPUT]
 * - MediaTaskRow: media task row for active or recent terminal jobs in BackgroundTasksPanel
 *
 * [POS]
 * BackgroundTasksPanel media section row renderer for async image/video jobs.
 */

import { Navigation } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { formatDistanceToNow } from 'date-fns';
import {
  IconCheckCircle,
  IconLoader,
  IconStop,
  IconXCircle,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import { getMediaTaskChatId, getMediaTaskPrompt } from '@/services/mediaTasks';
import type { Task } from '@/store/tasks/types';

interface MediaTaskRowProps {
  task: Task;
  variant?: 'active' | 'terminal';
  onCancel?: (taskId: string) => void;
  onNavigateChat: (chatId: string) => void;
}

const ACTIVE_STATUS_DOT: Record<'pending' | 'queued' | 'running', string> = {
  pending: 'bg-muted-foreground',
  queued: 'bg-amber-500 dark:bg-amber-400',
  running: 'bg-primary',
};

export function MediaTaskRow({
  task,
  variant = 'active',
  onCancel,
  onNavigateChat,
}: MediaTaskRowProps) {
  const t = useTranslations('backgroundTasks.media');
  const prompt = getMediaTaskPrompt(task.payload);
  const chatId = getMediaTaskChatId(task.payload);
  const typeLabel = task.task_type === 'video_generate' ? t('videoGenerate') : t('imageGenerate');
  const isTerminal = variant === 'terminal';
  const statusKey: keyof typeof ACTIVE_STATUS_DOT =
    task.status === 'pending' || task.status === 'queued' || task.status === 'running'
      ? task.status
      : 'running';

  const statusLabel = isTerminal
    ? task.status === 'succeeded'
      ? t('succeeded')
      : t('failed')
    : t(statusKey);

  const handleRowNavigate = () => {
    if (chatId) {
      onNavigateChat(chatId);
    }
  };

  const statusIcon = isTerminal ? (
    task.status === 'succeeded' ? (
      <IconCheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
    ) : (
      <IconXCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
    )
  ) : (
    <IconLoader
      className={cn(
        'mt-0.5 h-4 w-4 shrink-0',
        task.status === 'running' ? 'animate-spin text-primary' : 'text-muted-foreground',
      )}
    />
  );

  return (
    <div
      className={cn(
        'px-4 py-3 transition-colors hover:bg-muted/30',
        chatId && 'cursor-pointer',
      )}
      data-testid={`media-task-row-${task.task_id}`}
      data-variant={variant}
      onClick={chatId ? handleRowNavigate : undefined}
      onKeyDown={
        chatId
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                handleRowNavigate();
              }
            }
          : undefined
      }
      role={chatId ? 'button' : undefined}
      tabIndex={chatId ? 0 : undefined}
    >
      <div className="flex items-start gap-2.5">
        {statusIcon}
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm leading-snug text-foreground">
            {prompt || t('untitledPrompt')}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {!isTerminal && (
              <span className={cn('h-1.5 w-1.5 rounded-full', ACTIVE_STATUS_DOT[statusKey])} />
            )}
            <span>{typeLabel}</span>
            <span className="text-border">·</span>
            <span>{statusLabel}</span>
            <span className="text-border">·</span>
            <span>
              {formatDistanceToNow(new Date(task.updated_at), {
                addSuffix: true,
              })}
            </span>
          </div>

          {!isTerminal && task.status === 'running' && task.progress > 0 && (
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted/50">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${Math.min(100, Math.max(0, task.progress))}%` }}
              />
            </div>
          )}

          {!isTerminal && task.progress_message && (
            <p className="mt-1 line-clamp-1 text-xs text-muted-foreground/80">{task.progress_message}</p>
          )}

          {isTerminal && task.status === 'failed' && task.error?.message && (
            <p className="mt-1 line-clamp-2 text-xs text-destructive/80">{task.error.message}</p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-2">
            {!isTerminal && onCancel && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1 px-2 text-xs"
                onClick={(event) => {
                  event.stopPropagation();
                  onCancel(task.task_id);
                }}
                data-testid="media-task-cancel"
              >
                <IconStop className="h-3 w-3" />
                {t('cancel')}
              </Button>
            )}
            {chatId && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2 text-xs"
                onClick={(event) => {
                  event.stopPropagation();
                  onNavigateChat(chatId);
                }}
                data-testid="media-task-navigate"
              >
                <Navigation className="h-3 w-3" />
                {t('navigate')}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
