/**
 * [INPUT]
 * - @/services/taskEventStream::{subscribeTaskUpdateEvents,isTaskUpdateEventStreamOpen} (POS: multiplexed task SSE fan-out)
 *
 * [OUTPUT]
 * - useTasksSubscription / useTaskSubscription: Chat task card realtime state
 *
 * [POS]
 * Chat-side task SSE subscriber. Shares one browser EventSource with Panel, tray, and global media notify via taskEventStream.
 * Raises no notifications: useGlobalMediaTaskNotifications is the single owner of terminal media task notifications.
 */

import { useEffect, useMemo, useState } from 'react';
import type { Task } from '@/store/tasks/types';
import { isTaskUpdateEventStreamOpen, subscribeTaskUpdateEvents } from '@/services/taskEventStream';

export function useTasksSubscription(task_ids: string[]) {
  const [tasks, setTasks] = useState<Map<string, Task>>(new Map());

  const stableIds = useMemo(() => task_ids.join(','), [task_ids]);

  useEffect(() => {
    if (!stableIds) {
      return;
    }

    const ids = stableIds.split(',');
    let disposed = false;
    let nextSnapshotSyncAtMs = 0;

    const upsertTask = (task: Task) => {
      setTasks((prev) => {
        const next = new Map(prev);
        next.set(task.task_id, task);
        return next;
      });
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
