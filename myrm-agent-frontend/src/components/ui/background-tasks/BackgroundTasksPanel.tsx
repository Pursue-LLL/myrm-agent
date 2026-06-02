'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconLoader, IconCheckCircle, IconXCircle, IconBan, IconStop } from '@/components/ui/icons/PremiumIcons';
import { Navigation } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import {
  listBackgroundTasks,
  cancelBackgroundTask,
  steerBackgroundTask,
  type BackgroundTask,
} from '@/services/background-tasks';
import { formatDistanceToNow } from 'date-fns';

interface BackgroundTasksPanelProps {
  trigger: React.ReactNode;
}

const POLL_FAST_MS = 3_000;
const POLL_SLOW_MS = 30_000;
const IDLE_STOP_THRESHOLD = 3;

const STATUS_CONFIG = {
  running: {
    icon: IconLoader,
    className: 'text-primary animate-spin',
    dotColor: 'bg-primary',
  },
  completed: {
    icon: IconCheckCircle,
    className: 'text-emerald-500 dark:text-emerald-400',
    dotColor: 'bg-emerald-500 dark:bg-emerald-400',
  },
  failed: {
    icon: IconXCircle,
    className: 'text-destructive',
    dotColor: 'bg-destructive',
  },
  cancelled: {
    icon: IconBan,
    className: 'text-muted-foreground',
    dotColor: 'bg-muted-foreground',
  },
} as const;

export default function BackgroundTasksPanel({ trigger }: BackgroundTasksPanelProps) {
  const t = useTranslations('backgroundTasks');
  const [tasks, setTasks] = useState<BackgroundTask[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [steerTaskId, setSteerTaskId] = useState<string | null>(null);
  const [steerInput, setSteerInput] = useState('');
  const idleCountRef = useRef(0);

  const fetchTasks = useCallback(async () => {
    try {
      const result = await listBackgroundTasks();
      setTasks(result);
      const hasRunning = result.some((task) => task.status === 'running');
      idleCountRef.current = hasRunning ? 0 : idleCountRef.current + 1;
    } catch {
      // silent - panel is non-critical UI
    }
  }, []);

  // Panel open: fast polling (3s)
  useEffect(() => {
    if (!isOpen) return;
    idleCountRef.current = 0;
    fetchTasks();
    const interval = setInterval(fetchTasks, POLL_FAST_MS);
    return () => clearInterval(interval);
  }, [isOpen, fetchTasks]);

  // Panel closed: slow polling for badge accuracy (30s, stops after consecutive idle)
  useEffect(() => {
    if (isOpen) return;

    fetchTasks();

    const interval = setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      if (idleCountRef.current >= IDLE_STOP_THRESHOLD) return;
      fetchTasks();
    }, POLL_SLOW_MS);

    return () => clearInterval(interval);
  }, [isOpen, fetchTasks]);

  const handleCancel = async (taskId: string) => {
    try {
      await cancelBackgroundTask(taskId);
      toast.success(t('cancelSuccess'));
      fetchTasks();
    } catch {
      toast.error(t('cancelFailed'));
    }
  };

  const handleSteer = async (taskId: string) => {
    if (!steerInput.trim()) return;
    try {
      await steerBackgroundTask(taskId, steerInput.trim());
      toast.success(t('steerSuccess'));
      setSteerTaskId(null);
      setSteerInput('');
    } catch {
      toast.error(t('steerFailed'));
    }
  };

  const runningCount = tasks.filter((task) => task.status === 'running').length;

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <div className="relative">
          {trigger}
          {runningCount > 0 && (
            <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium text-primary-foreground">
              {runningCount}
            </span>
          )}
        </div>
      </PopoverTrigger>
      <PopoverContent
        className="w-[340px] p-0 border-border/50 bg-popover/95 backdrop-blur-xl sm:w-[380px]"
        align="end"
        sideOffset={8}
      >
        <div className="border-b border-border/50 px-4 py-3">
          <h3 className="text-sm font-medium text-foreground">{t('title')}</h3>
        </div>

        <div className="max-h-[360px] overflow-y-auto sm:max-h-[400px]">
          {tasks.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">{t('empty')}</div>
          ) : (
            <div className="divide-y divide-border/30">
              {tasks.map((task) => {
                const config = STATUS_CONFIG[task.status];
                const StatusIcon = config.icon;

                return (
                  <div key={task.task_id} className="px-4 py-3 transition-colors hover:bg-muted/30">
                    <div className="flex items-start gap-2.5">
                      <StatusIcon className={cn('mt-0.5 h-4 w-4 shrink-0', config.className)} />
                      <div className="min-w-0 flex-1">
                        <p className="line-clamp-2 text-sm leading-snug text-foreground">{task.prompt}</p>
                        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <span className={cn('h-1.5 w-1.5 rounded-full', config.dotColor)} />
                          <span>{t(task.status)}</span>
                          <span className="text-border">·</span>
                          <span>
                            {formatDistanceToNow(new Date(task.created_at * 1000), {
                              addSuffix: true,
                            })}
                          </span>
                        </div>

                        {task.result_preview && task.status === 'completed' && (
                          <p className="mt-1.5 line-clamp-2 rounded bg-muted/50 px-2 py-1 text-xs text-muted-foreground/80">
                            {task.result_preview}
                          </p>
                        )}

                        {task.status === 'running' && (
                          <div className="mt-2 flex items-center gap-1.5">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 px-2 text-xs text-destructive hover:text-destructive"
                              onClick={() => handleCancel(task.task_id)}
                            >
                              <IconStop className="mr-1 h-3 w-3" />
                              {t('cancel')}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 px-2 text-xs"
                              onClick={() => setSteerTaskId(steerTaskId === task.task_id ? null : task.task_id)}
                            >
                              <Navigation className="mr-1 h-3 w-3" />
                              {t('steer')}
                            </Button>
                          </div>
                        )}

                        {steerTaskId === task.task_id && (
                          <div className="mt-2 flex items-center gap-1.5">
                            <Input
                              className="h-7 text-xs"
                              placeholder={t('steerPlaceholder')}
                              value={steerInput}
                              onChange={(e) => setSteerInput(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleSteer(task.task_id);
                              }}
                            />
                            <Button
                              variant="default"
                              size="sm"
                              className="h-7 px-2 text-xs"
                              onClick={() => handleSteer(task.task_id)}
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
              })}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
