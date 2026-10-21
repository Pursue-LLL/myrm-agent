/**
 * [INPUT]
 * - @/services/kanban::getTask (POS: 看板 API 层)
 * - ./kanban-styles::TaskDepInfo (POS: 依赖任务摘要类型)
 *
 * [OUTPUT]
 * - resolveTaskDepInfos: 把依赖任务 id 解析为 {标题, 状态}
 *
 * [POS]
 * 先查当前看板的任务列表，查不到再按 id 向服务端取；仍取不到时用 id 前 8 位和 archived 兜底，保证依赖列表不空缺。
 */
import { getTask } from '@/services/kanban';
import type { KanbanTask } from '@/services/kanban';
import type { TaskDepInfo } from './kanban-styles';

export async function resolveTaskDepInfos(ids: string[], currentTasks: KanbanTask[]): Promise<TaskDepInfo[]> {
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
