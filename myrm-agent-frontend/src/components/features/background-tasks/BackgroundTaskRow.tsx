'use client';

import { Navigation, FileText } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { formatDistanceToNow } from 'date-fns';
import { IconStop } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import type { BackgroundTask } from '@/services/background-tasks';
import { STATUS_CONFIG } from './backgroundTasksPanel.constants';

interface BackgroundTaskRowProps {
  task: BackgroundTask;
  allowSteer: boolean;
  steerTaskId: string | null;
  steerInput: string;
  onSteerInputChange: (value: string) => void;
  onToggleSteer: (taskId: string) => void;
  onSteer: (taskId: string) => void;
  onCancel: (taskId: string) => void;
  onNavigateChat: (chatId: string) => void;
  onViewVaultLog?: (chatId: string, vaultLogRef: string) => void;
}

export function BackgroundTaskRow({
  task,
  allowSteer,
  steerTaskId,
  steerInput,
  onSteerInputChange,
  onToggleSteer,
  onSteer,
  onCancel,
  onNavigateChat,
  onViewVaultLog,
}: BackgroundTaskRowProps) {
  const t = useTranslations('backgroundTasks');
  const tChat = useTranslations('chat');
  const config = STATUS_CONFIG[task.status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.running;
  const StatusIcon = config.icon;
  const canViewVaultLog = Boolean(task.vault_log_ref && task.chat_id && onViewVaultLog);
  const LogActionIcon = canViewVaultLog ? FileText : Navigation;

  const handleSecondaryAction = () => {
    if (!task.chat_id) return;
    if (canViewVaultLog) {
      onViewVaultLog!(task.chat_id, task.vault_log_ref!);
      return;
    }
    onNavigateChat(task.chat_id);
  };

  return (
    <div className="px-4 py-3 transition-colors hover:bg-muted/30">
      <div className="flex items-start gap-2.5">
        <StatusIcon className={cn('mt-0.5 h-4 w-4 shrink-0', config.className)} />
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm leading-snug text-foreground">{task.prompt}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className={cn('h-1.5 w-1.5 rounded-full', config.dotColor)} />
            <span>{t(task.status)}</span>
            <span className="text-border">·</span>
            <span>
              {formatDistanceToNow(new Date(task.created_at * 1000), {
                addSuffix: true,
              })}
            </span>
            {task.kind === 'shell' && task.pid != null && (
              <>
                <span className="text-border">·</span>
                <span>{t('shellPid', { pid: task.pid })}</span>
              </>
            )}
            {task.exit_code != null && task.status !== 'running' && (
              <>
                <span className="text-border">·</span>
                <span>{t('exitCode', { code: task.exit_code })}</span>
              </>
            )}
          </div>

          {task.error_category && (
            <p className="mt-1 text-xs text-destructive/90">
              {tChat(`errorCategories.${task.error_category}`, { defaultValue: task.error_category })}
            </p>
          )}

          {task.progress_percent != null && task.status === 'running' && (
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${Math.min(100, Math.max(0, task.progress_percent))}%` }}
              />
            </div>
          )}

          {task.status === 'orphaned' && (
            <p className="mt-1 text-xs text-amber-600/90 dark:text-amber-400/90">{t('orphanedHint')}</p>
          )}

          {task.result_preview && (
            <p className="mt-1.5 line-clamp-2 rounded bg-muted/50 px-2 py-1 text-xs text-muted-foreground/80">
              {task.result_preview}
            </p>
          )}

          {task.status === 'running' ? (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {task.chat_id && (
                <>
                  {canViewVaultLog ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs"
                      onClick={handleSecondaryAction}
                    >
                      <LogActionIcon className="mr-1 h-3 w-3" />
                      {t('viewFullLog')}
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs"
                      onClick={() => onNavigateChat(task.chat_id!)}
                    >
                      <LogActionIcon className="mr-1 h-3 w-3" />
                      {t('navigate')}
                    </Button>
                  )}
                </>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs text-destructive hover:text-destructive"
                onClick={() => onCancel(task.task_id)}
              >
                <IconStop className="mr-1 h-3 w-3" />
                {t('cancel')}
              </Button>
              {allowSteer && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={() => onToggleSteer(task.task_id)}
                >
                  <Navigation className="mr-1 h-3 w-3" />
                  {t('steer')}
                </Button>
              )}
            </div>
          ) : (
            task.chat_id && (
              <div className="mt-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={handleSecondaryAction}
                >
                  <LogActionIcon className="mr-1 h-3 w-3" />
                  {canViewVaultLog ? t('viewFullLog') : t('navigate')}
                </Button>
              </div>
            )
          )}

          {allowSteer && steerTaskId === task.task_id && (
            <div className="mt-2 flex items-center gap-1.5">
              <Input
                className="h-7 text-xs"
                placeholder={t('steerPlaceholder')}
                value={steerInput}
                onChange={(e) => onSteerInputChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onSteer(task.task_id);
                }}
              />
              <Button
                variant="default"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => onSteer(task.task_id)}
                disabled={!steerInput.trim()}
              >
                <Navigation className="h-3 w-3" />
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
