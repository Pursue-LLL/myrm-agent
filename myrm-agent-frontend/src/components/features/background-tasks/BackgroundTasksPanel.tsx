'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Terminal } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { toast } from '@/lib/utils/toast';
import { fetchWithTimeout } from '@/lib/api';
import {
  listBackgroundTasks,
  cancelBackgroundTask,
  steerBackgroundTask,
  type BackgroundTask,
} from '@/services/background-tasks';
import { subscribeBackgroundTasksChanged } from '@/services/backgroundTasksRefresh';
import { ActiveGoalsSection } from './ActiveGoalsSection';
import { BackgroundTaskRow } from './BackgroundTaskRow';
import {
  type ActiveGoal,
  IDLE_STOP_THRESHOLD,
  POLL_FAST_MS,
  POLL_SLOW_MS,
} from './backgroundTasksPanel.constants';

interface BackgroundTasksPanelProps {
  trigger: React.ReactNode;
}

export default function BackgroundTasksPanel({ trigger }: BackgroundTasksPanelProps) {
  const t = useTranslations('backgroundTasks');
  const router = useRouter();
  const [tasks, setTasks] = useState<BackgroundTask[]>([]);
  const [registryEphemeral, setRegistryEphemeral] = useState(false);
  const [activeGoals, setActiveGoals] = useState<ActiveGoal[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [steerTaskId, setSteerTaskId] = useState<string | null>(null);
  const [steerInput, setSteerInput] = useState('');
  const idleCountRef = useRef(0);

  const fetchTasks = useCallback(async () => {
    try {
      const result = await listBackgroundTasks();
      setTasks(result.tasks);
      setRegistryEphemeral(Boolean(result.registry_ephemeral));
      const hasRunning = result.tasks.some((task) => task.status === 'running');
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

  useEffect(() => {
    if (!isOpen) return;
    idleCountRef.current = 0;
    fetchTasks();
    fetchActiveGoals();
    const interval = setInterval(() => {
      fetchTasks();
      fetchActiveGoals();
    }, POLL_FAST_MS);
    return () => clearInterval(interval);
  }, [isOpen, fetchTasks, fetchActiveGoals]);

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

  const handleToggleSteer = (taskId: string) => {
    setSteerTaskId((current) => (current === taskId ? null : taskId));
    setSteerInput('');
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
          {registryEphemeral && (
            <p className="mt-1 text-xs text-muted-foreground/80">{t('ephemeralRegistryNotice')}</p>
          )}
        </div>

        <div className="max-h-[360px] overflow-y-auto sm:max-h-[400px]">
          <ActiveGoalsSection
            goals={activeGoals}
            onNavigateChat={handleNavigateChat}
            onGoalAction={handleGoalAction}
          />

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
                    {shellTasks.map((task) => (
                      <BackgroundTaskRow
                        key={task.task_id}
                        task={task}
                        allowSteer={false}
                        steerTaskId={steerTaskId}
                        steerInput={steerInput}
                        onSteerInputChange={setSteerInput}
                        onToggleSteer={handleToggleSteer}
                        onSteer={handleSteer}
                        onCancel={handleCancel}
                        onNavigateChat={handleNavigateChat}
                      />
                    ))}
                  </div>
                </div>
              )}

              {agentTasks.length > 0 && (
                <div className="border-b border-border/30">
                  <div className="px-4 py-2 text-xs font-medium text-muted-foreground/70 uppercase tracking-wide">
                    {t('agentSection')} ({agentTasks.length})
                  </div>
                  <div className="divide-y divide-border/20">
                    {agentTasks.map((task) => (
                      <BackgroundTaskRow
                        key={task.task_id}
                        task={task}
                        allowSteer
                        steerTaskId={steerTaskId}
                        steerInput={steerInput}
                        onSteerInputChange={setSteerInput}
                        onToggleSteer={handleToggleSteer}
                        onSteer={handleSteer}
                        onCancel={handleCancel}
                        onNavigateChat={handleNavigateChat}
                      />
                    ))}
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
