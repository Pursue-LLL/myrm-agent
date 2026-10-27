'use client';

import { useMemo } from 'react';
import type { BackgroundTask } from '@/services/background-tasks';
import type { Task } from '@/store/tasks/types';
import type { ActiveGoal } from './backgroundTasksPanel.constants';

interface PanelItems {
  activeGoals: ActiveGoal[];
  mediaTasks: Task[];
  recentTerminalMediaTasks: Task[];
  tasks: BackgroundTask[];
}

/** Whether any of the item's search texts contains the query (already lower-cased). */
const matchesAny = (query: string, texts: readonly (string | null | undefined)[]): boolean =>
  texts.some((text) => (text ?? '').toLowerCase().includes(query));

const matchesMediaTask = (task: Task, query: string): boolean =>
  matchesAny(query, [String(task.payload?.prompt ?? ''), task.task_type, task.status, task.task_id]);

const matchesBackgroundTask = (task: BackgroundTask, query: string): boolean =>
  matchesAny(query, [task.prompt, task.status, task.task_id, task.result_preview]);

/**
 * The panel's items that match the search box: goals (objective, status, chat), media tasks (prompt, type, status, id)
 * and Agent / long-running tasks (prompt, status, id, result). An empty search keeps everything.
 */
export function useBackgroundTasksSearch(searchQuery: string, items: PanelItems) {
  const query = searchQuery.trim().toLowerCase();
  const { activeGoals, mediaTasks, recentTerminalMediaTasks, tasks } = items;

  return useMemo(() => {
    const keep = <T>(list: T[], matches: (item: T) => boolean): T[] => (query ? list.filter(matches) : list);
    return {
      filteredActiveGoals: keep(activeGoals, (goal) =>
        matchesAny(query, [goal.objective, goal.status, goal.session_id]),
      ),
      filteredMediaTasks: keep(mediaTasks, (task) => matchesMediaTask(task, query)),
      filteredRecentTerminalMediaTasks: keep(recentTerminalMediaTasks, (task) => matchesMediaTask(task, query)),
      agentTasks: keep(
        tasks.filter((task) => (task.kind ?? 'agent') !== 'shell'),
        (task) => matchesBackgroundTask(task, query),
      ),
      shellTasks: keep(
        tasks.filter((task) => task.kind === 'shell'),
        (task) => matchesBackgroundTask(task, query),
      ),
    };
  }, [query, activeGoals, mediaTasks, recentTerminalMediaTasks, tasks]);
}
