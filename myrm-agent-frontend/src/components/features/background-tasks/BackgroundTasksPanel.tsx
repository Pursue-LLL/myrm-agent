'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { IconLoader, IconCheckCircle, IconXCircle, IconBan, IconStop, IconClock } from '@/components/features/icons/PremiumIcons';
import { Navigation, Target, Terminal } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { fetchWithTimeout } from '@/lib/api';
import {
  listBackgroundTasks,
  cancelBackgroundTask,
  steerBackgroundTask,
  type BackgroundTask,
} from '@/services/background-tasks';
import { subscribeBackgroundTasksChanged } from '@/services/backgroundTasksRefresh';
import { formatDistanceToNow } from 'date-fns';

interface ActiveGoal {
  goal_id: string;
  session_id: string;
  objective: string;
  status: string;
  tokens_used: number;
  created_at: string;
}

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
  timed_out: {
    icon: IconClock,
    className: 'text-amber-500 dark:text-amber-400',
    dotColor: 'bg-amber-500 dark:bg-amber-400',
  },
  cancelled: {
    icon: IconBan,
    className: 'text-muted-foreground',
    dotColor: 'bg-muted-foreground',
  },
} as const;

const GOAL_STATUS_STYLES: Record<string, { dotColor: string; i18nKey: string }> = {
  active: { dotColor: 'bg-primary', i18nKey: 'goalStatusActive' },
  paused: { dotColor: 'bg-amber-500', i18nKey: 'goalStatusPaused' },
  pending_approval: { dotColor: 'bg-violet-500', i18nKey: 'goalStatusPendingApproval' },
  budget_limited: { dotColor: 'bg-orange-500', i18nKey: 'goalStatusBudgetLimited' },
  needs_human_review: { dotColor: 'bg-rose-500', i18nKey: 'goalStatusNeedsReview' },
  queued: { dotColor: 'bg-muted-foreground', i18nKey: 'goalStatusQueued' },
};

export default function BackgroundTasksPanel({ trigger }: BackgroundTasksPanelProps) {
  const t = useTranslations('backgroundTasks');
  const router = useRouter();
  const [tasks, setTasks] = useState<BackgroundTask[]>([]);
  const [activeGoals, setActiveGoals] = useState<ActiveGoal[]>([]);
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

  const fetchActiveGoals = useCallback(async () => {
    try {
      const res = await fetchWithTimeout('/goals/active');
      if (!res.ok) return;
      const data = await res.json();
      setActiveGoals(data.goals || []);
    } catch {
      // silent - non-critical
    }
  }, []);

  // Panel open: fast polling (3s)
  useEffect(() => {
    if (!isOpen) return;
    idleCountRef.current = 0;
    fetchTasks();
    fetchActiveGoals();
    const interval = setInterval(() => { fetchTasks(); fetchActiveGoals(); }, POLL_FAST_MS);
    return () => clearInterval(interval);
  }, [isOpen, fetchTasks, fetchActiveGoals]);

  // Panel closed: slow polling for badge accuracy (30s, stops after consecutive idle)
  useEffect(() => {
    if (isOpen) return;

    fetchTasks();
    fetchActiveGoals();

    const interval = setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      if (idleCountRef.current >= IDLE_STOP_THRESHOLD) return;
      fetchTasks();
      fetchActiveGoals();
    }, POLL_SLOW_MS);

    return () => clearInterval(interval);
  }, [isOpen, fetchTasks, fetchActiveGoals]);

  useEffect(() => subscribeBackgroundTasksChanged(fetchTasks), [fetchTasks]);

  const agentTasks = useMemo(
    () => tasks.filter((task) => (task.kind ?? 'agent') !== 'shell'),
    [tasks],
  );
  const shellTasks = useMemo(
    () => tasks.filter((task) => task.kind === 'shell'),
    [tasks],
  );

  const handleGoalAction = async (sessionId: string, action: string) => {
    try {
      const res = await fetchWithTimeout(`/goals/${sessionId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      if (!res.ok) throw new Error('Failed');
      toast.success(t('goalActionSuccess'));
      fetchActiveGoals();
    } catch {
      toast.error(t('cancelFailed'));
    }
  };

  const handleCancel = async (taskId: string) => {
    try {
      await cancelBackgroundTask(taskId);
      toast.success(t('cancelSuccess'));
      fetchTasks();
    } catch {
      toast.error(t('cancelFailed'));
    }
  };

  const handleNavigateChat = (chatId: string) => {
    setIsOpen(false);
    router.push(`/chat/${chatId}`);
  };

  const renderTaskRow = (task: BackgroundTask, options: { allowSteer: boolean }) => {
    const config = STATUS_CONFIG[task.status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.running;
    const StatusIcon = config.icon;

    return (
      <div key={task.task_id} className="px-4 py-3 transition-colors hover:bg-muted/30">
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
            </div>

            {task.progress_percent != null && task.status === 'running' && (
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${Math.min(100, Math.max(0, task.progress_percent))}%` }}
                />
              </div>
            )}

            {task.result_preview && (task.status === 'completed' || task.status === 'failed' || task.status === 'timed_out') && (
              <p className="mt-1.5 line-clamp-2 rounded bg-muted/50 px-2 py-1 text-xs text-muted-foreground/80">
                {task.result_preview}
              </p>
            )}

            {task.status === 'running' && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {task.chat_id && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    onClick={() => handleNavigateChat(task.chat_id!)}
                  >
                    <Navigation className="mr-1 h-3 w-3" />
                    {t('navigate')}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs text-destructive hover:text-destructive"
                  onClick={() => handleCancel(task.task_id)}
                >
                  <IconStop className="mr-1 h-3 w-3" />
                  {t('cancel')}
                </Button>
                {options.allowSteer && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    onClick={() => setSteerTaskId(steerTaskId === task.task_id ? null : task.task_id)}
                  >
                    <Navigation className="mr-1 h-3 w-3" />
                    {t('steer')}
                  </Button>
                )}
              </div>
            )}

            {options.allowSteer && steerTaskId === task.task_id && (
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
  const totalBadge = runningCount + activeGoals.length;

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <Tooltip open={isOpen ? false : undefined}>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <div className="relative inline-flex cursor-pointer">
              {trigger}
              {totalBadge > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium text-primary-foreground">
                  {totalBadge}
                </span>
              )}
            </div>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent side="right">{t('title')}</TooltipContent>
      </Tooltip>
      <PopoverContent
        className="w-[340px] p-0 border-border/50 bg-popover/95 backdrop-blur-xl sm:w-[380px]"
        align="end"
        sideOffset={8}
      >
        <div className="border-b border-border/50 px-4 py-3">
          <h3 className="text-sm font-medium text-foreground">{t('title')}</h3>
        </div>

        <div className="max-h-[360px] overflow-y-auto sm:max-h-[400px]">
          {/* Active Goals Section */}
          {activeGoals.length > 0 && (
            <div className="border-b border-border/30">
              <div className="px-4 py-2 text-xs font-medium text-muted-foreground/70 uppercase tracking-wide">
                <Target className="mr-1 inline h-3 w-3" />
                {t('goalsSection')} ({activeGoals.length})
              </div>
              <div className="divide-y divide-border/20">
                {activeGoals.map((goal) => {
                  const style = GOAL_STATUS_STYLES[goal.status] ?? GOAL_STATUS_STYLES.active;
                  return (
                    <div key={goal.goal_id} className="px-4 py-2.5 transition-colors hover:bg-muted/30">
                      <div className="flex items-start gap-2.5">
                        <Target className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        <div className="min-w-0 flex-1">
                          <p className="line-clamp-2 text-sm leading-snug text-foreground">{goal.objective}</p>
                          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                            <span className={cn('h-1.5 w-1.5 rounded-full', style.dotColor)} />
                            <span>{t(style.i18nKey)}</span>
                            <span className="text-border">·</span>
                            <span>{formatDistanceToNow(new Date(goal.created_at), { addSuffix: true })}</span>
                            {goal.tokens_used > 0 && (
                              <>
                                <span className="text-border">·</span>
                                <span>{goal.tokens_used >= 1000 ? `${(goal.tokens_used / 1000).toFixed(1)}k` : goal.tokens_used} tokens</span>
                              </>
                            )}
                          </div>
                          <div className="mt-1.5 flex items-center gap-1.5">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 px-2 text-xs"
                              onClick={() => router.push(`/chat/${goal.session_id}`)}
                            >
                              <Navigation className="mr-1 h-3 w-3" />
                              {t('navigate')}
                            </Button>
                            {goal.status === 'active' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 px-2 text-xs text-amber-600 dark:text-amber-400"
                                onClick={() => handleGoalAction(goal.session_id, 'pause')}
                              >
                                {t('goalPause')}
                              </Button>
                            )}
                            {goal.status === 'paused' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 px-2 text-xs text-emerald-600 dark:text-emerald-400"
                                onClick={() => handleGoalAction(goal.session_id, 'resume')}
                              >
                                {t('goalResume')}
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 px-2 text-xs text-destructive hover:text-destructive"
                              onClick={() => handleGoalAction(goal.session_id, 'cancel')}
                            >
                              <IconStop className="mr-1 h-3 w-3" />
                              {t('cancel')}
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Background Tasks Section */}
          {tasks.length === 0 && activeGoals.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">{t('empty')}</div>
          ) : (
            <>
              {shellTasks.length > 0 && (
                <div className="border-b border-border/30">
                  <div className="px-4 py-2 text-xs font-medium text-muted-foreground/70 uppercase tracking-wide">
                    <Terminal className="mr-1 inline h-3 w-3" />
                    {t('shellSection')} ({shellTasks.length})
                  </div>
                  <div className="divide-y divide-border/20">
                    {shellTasks.map((task) => renderTaskRow(task, { allowSteer: false }))}
                  </div>
                </div>
              )}

              {agentTasks.length > 0 && (
                <div className="border-b border-border/30">
                  <div className="px-4 py-2 text-xs font-medium text-muted-foreground/70 uppercase tracking-wide">
                    {t('agentSection')} ({agentTasks.length})
                  </div>
                  <div className="divide-y divide-border/20">
                    {agentTasks.map((task) => renderTaskRow(task, { allowSteer: true }))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
