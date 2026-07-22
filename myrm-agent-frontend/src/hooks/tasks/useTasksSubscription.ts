/**
 * Hook for subscribing to task status updates via SSE.
 *
 * Features:
 * - Single SSE connection for multiple tasks (batch subscription)
 * - Automatic fallback to polling if SSE disconnects
 * - Task completion notifications
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import type { Task } from '@/store/tasks/types';
import { notificationService } from '@/services/notification';

export function useTasksSubscription(task_ids: string[]) {
  const [tasks, setTasks] = useState<Map<string, Task>>(new Map());
  const t = useTranslations('notifications');

  const stableIds = useMemo(() => task_ids.join(','), [task_ids]);

  useEffect(() => {
    if (!stableIds) return;

    const ids = stableIds.split(',');
    const notifiedTerminalTaskIds = new Set<string>();
    let disposed = false;
    let nextMalformedSyncAtMs = 0;

    const upsertTask = (task: Task) => {
      setTasks((prev) => {
        const next = new Map(prev);
        next.set(task.task_id, task);
        return next;
      });
    };

    const notifyIfTerminal = (task: Task) => {
      if (task.status !== 'succeeded' && task.status !== 'failed') {
        return;
      }
      const dedupeKey = `${task.task_id}:${task.status}`;
      if (notifiedTerminalTaskIds.has(dedupeKey)) {
        return;
      }
      notifiedTerminalTaskIds.add(dedupeKey);

      const title =
        task.status === 'succeeded'
          ? t('taskCompleted', { taskType: task.task_type })
          : t('taskFailed', { taskType: task.task_type });
      const body = task.status === 'failed' ? task.error?.message || t('taskUnknownError') : undefined;
      notificationService.notify(title, { body });
    };

    const fetchTaskById = async (taskId: string): Promise<Task | null> => {
      try {
        const response = await fetch(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
        if (!response.ok) {
          return null;
        }
        return (await response.json()) as Task;
      } catch (error) {
        console.error('Failed to fetch task detail:', error);
        return null;
      }
    };

    const syncSubscribedTasks = async () => {
      try {
        const response = await fetch(`/api/v1/tasks?ids=${encodeURIComponent(stableIds)}&detail=true`);
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as { tasks?: Task[] };
        if (disposed || !Array.isArray(data.tasks)) {
          return;
        }
        const tasksMap = new Map<string, Task>();
        for (const task of data.tasks) {
          tasksMap.set(task.task_id, task);
          notifyIfTerminal(task);
        }
        setTasks(tasksMap);
      } catch (error) {
        console.error('Failed to poll tasks:', error);
      }
    };

    const eventSource = new EventSource('/api/v1/tasks/stream');

    eventSource.addEventListener('task_update', (event) => {
      let eventData: { task_id?: string } | null = null;
      try {
        const parsed = JSON.parse(event.data) as unknown;
        if (!parsed || typeof parsed !== 'object') {
          throw new Error('task_update SSE payload is not an object');
        }
        eventData = parsed as { task_id?: string };
      } catch (error) {
        console.warn('Failed to parse task_update SSE payload; syncing subscribed tasks snapshot.', error);
        const now = Date.now();
        if (now >= nextMalformedSyncAtMs) {
          nextMalformedSyncAtMs = now + 1000;
          void syncSubscribedTasks();
        }
        return;
      }

      if (!eventData.task_id || !ids.includes(eventData.task_id)) {
        return;
      }
      void fetchTaskById(eventData.task_id).then((task) => {
        if (!task || disposed) {
          return;
        }
        upsertTask(task);
        notifyIfTerminal(task);
      });
    });

    void syncSubscribedTasks();

    const pollInterval = setInterval(async () => {
      if (eventSource.readyState !== EventSource.OPEN) {
        await syncSubscribedTasks();
      }
    }, 5000);

    return () => {
      disposed = true;
      eventSource.close();
      clearInterval(pollInterval);
    };
  }, [stableIds]);

  return tasks;
}

export function useTaskSubscription(task_id: string) {
  const tasks = useTasksSubscription([task_id]);
  return tasks.get(task_id);
}
