/**
 * [INPUT]
 * - @/services/taskEventStream::{subscribeTaskUpdateEvents,isTaskUpdateEventStreamOpen} (POS: multiplexed task SSE fan-out)
 * - @/services/notification::notificationService (POS: Web Notification + toast fallback)
 * - @/store/useConfigStore::enableWebNotifications (POS: personal notification preference gate)
 *
 * [OUTPUT]
 * - useTasksSubscription / useTaskSubscription: Chat task card realtime state + terminal notifications
 *
 * [POS]
 * Chat-side task SSE subscriber. Shares one browser EventSource with Panel, tray, and global media notify via taskEventStream.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import type { Task } from '@/store/tasks/types';
import { notificationService } from '@/services/notification';
import {
  isTaskUpdateEventStreamOpen,
  subscribeTaskUpdateEvents,
} from '@/services/taskEventStream';
import useConfigStore from '@/store/useConfigStore';

export function useTasksSubscription(task_ids: string[]) {
  const [tasks, setTasks] = useState<Map<string, Task>>(new Map());
  const t = useTranslations('notifications');

  const stableIds = useMemo(() => task_ids.join(','), [task_ids]);

  useEffect(() => {
    if (!stableIds) return;

    const ids = stableIds.split(',');
    const notifiedTerminalTaskIds = new Set<string>();
    let disposed = false;
    let nextSnapshotSyncAtMs = 0;

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
      if (!useConfigStore.getState().enableWebNotifications) {
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

    const requestSnapshotSync = () => {
      const now = Date.now();
      if (now < nextSnapshotSyncAtMs) {
        return;
      }
      nextSnapshotSyncAtMs = now + 1000;
      void syncSubscribedTasks();
    };

    const unsubscribe = subscribeTaskUpdateEvents((eventData) => {
      if (eventData.sync_required === true) {
        requestSnapshotSync();
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
      if (!isTaskUpdateEventStreamOpen()) {
        await syncSubscribedTasks();
      }
    }, 5000);

    return () => {
      disposed = true;
      unsubscribe();
      clearInterval(pollInterval);
    };
  }, [stableIds]);

  return tasks;
}

export function useTaskSubscription(task_id: string) {
  const tasks = useTasksSubscription([task_id]);
  return tasks.get(task_id);
}
