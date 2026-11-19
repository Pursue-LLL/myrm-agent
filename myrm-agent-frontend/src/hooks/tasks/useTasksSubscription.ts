/**
 * [INPUT]
 * - @/services/taskEventStream::{subscribeTaskUpdateEvents,isTaskUpdateEventStreamOpen} (POS: multiplexed task SSE fan-out)
 *
 * [OUTPUT]
 * - useTasksSubscription: Chat task card realtime state for several tasks
 * - useTaskSubscription: The same for one task; `undefined` while loading, `null` once the server confirmed the task no longer exists
 *
 * [POS]
 * Chat-side task SSE subscriber. Shares one browser EventSource with Panel, tray, and global media notify via taskEventStream.
 * Raises no notifications: useGlobalMediaTaskNotifications is the single owner of terminal media task notifications.
 * A task is reported missing only by a snapshot that came back without it, never by a failed request, so a flaky
 * network cannot turn a live task into an expired one.
 */

import { useEffect, useMemo, useState } from 'react';
import type { Task } from '@/store/tasks/types';
import { isTaskUpdateEventStreamOpen, subscribeTaskUpdateEvents } from '@/services/taskEventStream';

function useTaskSnapshots(task_ids: string[]): { tasks: Map<string, Task>; missing: ReadonlySet<string> } {
  const [tasks, setTasks] = useState<Map<string, Task>>(new Map());
  const [missing, setMissing] = useState<ReadonlySet<string>>(new Set());

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
      setMissing((prev) => {
        if (!prev.has(task.task_id)) {
          return prev;
        }
        const next = new Set(prev);
        next.delete(task.task_id);
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
        setMissing(new Set(ids.filter((id) => !tasksMap.has(id))));
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

  return { tasks, missing };
}

export function useTasksSubscription(task_ids: string[]) {
  return useTaskSnapshots(task_ids).tasks;
}

export function useTaskSubscription(task_id: string): Task | null | undefined {
  const { tasks, missing } = useTaskSnapshots([task_id]);
  return tasks.get(task_id) ?? (missing.has(task_id) ? null : undefined);
}
