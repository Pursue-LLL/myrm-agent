/**
 * [INPUT]
 * - @/services/mediaTasks::{listActiveMediaTasks,listRecentTerminalMediaTasks} (POS: media task REST lists)
 * - @/services/taskEventStream::subscribeTaskUpdateEvents (POS: multiplexed task SSE fan-out)
 *
 * [OUTPUT]
 * - useMediaBackgroundTasks: active + recent terminal media task state for BackgroundTasksPanel
 *
 * [POS]
 * Panel-side media task state hook. Polls active and recent terminal jobs; refreshes on shared task SSE updates.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { listActiveMediaTasks, listRecentTerminalMediaTasks } from '@/services/mediaTasks';
import { subscribeTaskUpdateEvents } from '@/services/taskEventStream';
import type { Task } from '@/store/tasks/types';

export function useMediaBackgroundTasks() {
  const [mediaTasks, setMediaTasks] = useState<Task[]>([]);
  const [recentTerminalMediaTasks, setRecentTerminalMediaTasks] = useState<Task[]>([]);
  const disposedRef = useRef(false);

  const refetchMediaTasks = useCallback(async () => {
    try {
      const active = await listActiveMediaTasks();
      if (disposedRef.current) {
        return;
      }
      setMediaTasks(active);
      const activeIds = new Set(active.map((task) => task.task_id));
      const recent = await listRecentTerminalMediaTasks(activeIds);
      if (!disposedRef.current) {
        setRecentTerminalMediaTasks(recent);
      }
    } catch {
      // non-critical panel data
    }
  }, []);

  useEffect(() => {
    disposedRef.current = false;
    return () => {
      disposedRef.current = true;
    };
  }, []);

  useEffect(() => {
    let nextSnapshotSyncAtMs = 0;

    const requestSnapshotSync = () => {
      const now = Date.now();
      if (now < nextSnapshotSyncAtMs) {
        return;
      }
      nextSnapshotSyncAtMs = now + 1000;
      void refetchMediaTasks();
    };

    return subscribeTaskUpdateEvents(() => {
      requestSnapshotSync();
    });
  }, [refetchMediaTasks]);

  return { mediaTasks, recentTerminalMediaTasks, refetchMediaTasks };
}
