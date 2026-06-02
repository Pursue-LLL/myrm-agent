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

    const eventSource = new EventSource('/api/v1/tasks/stream');

    eventSource.addEventListener('task_update', (event) => {
      const data = JSON.parse(event.data) as Task;

      if (ids.includes(data.task_id)) {
        setTasks((prev) => {
          const next = new Map(prev);
          next.set(data.task_id, data);
          return next;
        });

        if (data.status === 'succeeded' || data.status === 'failed') {
          const title =
            data.status === 'succeeded'
              ? t('taskCompleted', { taskType: data.task_type })
              : t('taskFailed', { taskType: data.task_type });
          const body = data.status === 'failed' ? data.error?.message || t('taskUnknownError') : undefined;
          notificationService.notify(title, { body });
        }
      }
    });

    const pollInterval = setInterval(async () => {
      if (eventSource.readyState !== EventSource.OPEN) {
        try {
          const response = await fetch(`/api/v1/tasks?ids=${stableIds}`);
          const data = await response.json();

          const tasksMap = new Map<string, Task>();
          for (const task of data.tasks) {
            tasksMap.set(task.task_id, task);
          }
          setTasks(tasksMap);
        } catch (error) {
          console.error('Failed to poll tasks:', error);
        }
      }
    }, 5000);

    return () => {
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
