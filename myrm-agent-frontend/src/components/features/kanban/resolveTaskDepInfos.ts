import { getTask } from '@/services/kanban';
import type { KanbanTask } from '@/services/kanban';
import type { TaskDepInfo } from './kanban-styles';

export async function resolveTaskDepInfos(
  ids: string[],
  currentTasks: KanbanTask[],
): Promise<TaskDepInfo[]> {
  const infos: TaskDepInfo[] = [];
  for (const id of ids) {
    const local = currentTasks.find((tk) => tk.task_id === id);
    if (local) {
      infos.push({ task_id: id, title: local.title, status: local.status });
    } else {
      try {
        const remote = await getTask(id);
        infos.push({ task_id: id, title: remote.title, status: remote.status });
      } catch {
        infos.push({ task_id: id, title: id.slice(0, 8), status: 'archived' });
      }
    }
  }
  return infos;
}
