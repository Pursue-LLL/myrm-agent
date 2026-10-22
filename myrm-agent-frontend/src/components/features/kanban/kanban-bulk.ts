/**
 * [INPUT]
 * - @/services/kanban::bulkAction, BulkAction (POS: 看板批量接口客户端)
 * - sonner::toast (POS: 结果提示)
 *
 * [OUTPUT]
 * - BULK_CHUNK_SIZE: 单次请求携带的任务数上限
 * - runBulkAction: 分段发起批量请求并汇总提示，返回未成功的任务 id
 *
 * [POS]
 * 批量工具栏与批量拖拽共用的执行入口，两条路径因此有同一套结果语义：批量请求允许部分成功，
 * 成功与部分失败各给一条汇总提示，逐条的服务端错误原文不透出；失败的任务 id 交还调用方，
 * 由它让这些任务继续保持选中以便原地重试。选中的任务按 BULK_CHUNK_SIZE 分段、顺序发送，每段一次请求。
 */
import type { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { bulkAction, type BulkAction } from '@/services/kanban';

interface RunBulkActionOptions {
  boardId: string;
  taskIds: string[];
  action: BulkAction;
  params?: Record<string, string>;
  confirm?: boolean;
  t: ReturnType<typeof useTranslations<'kanban'>>;
}

/**
 * 单次请求携带的任务数上限，等于服务端 `BulkActionRequest.task_ids` 的 100 条上限。服务端逐条处理是毫秒级：
 * 归档带分支的任务时清理 worktree、移到「已完成」时合并分支都在后台执行，不占用请求，分段只受这个上限约束。
 */
export const BULK_CHUNK_SIZE = 100;

/**
 * 返回未成功的任务 id；没有任务时什么都不发、不提示，返回空数组。第一段请求就失败（网络、服务端异常）时
 * 已提示本地化错误并返回 `null`，此时没有任何任务被确认处理，调用方应当回滚乐观更新。
 * 中途某一段失败时，前面的分段已在服务端生效：该段与其后的任务算作未成功，一并交还调用方。
 */
export async function runBulkAction({
  boardId,
  taskIds,
  action,
  params = {},
  confirm = false,
  t,
}: RunBulkActionOptions): Promise<string[] | null> {
  if (taskIds.length === 0) {
    return [];
  }
  let succeeded = 0;
  const failedTaskIds: string[] = [];

  for (let start = 0; start < taskIds.length; start += BULK_CHUNK_SIZE) {
    try {
      const result = await bulkAction(boardId, taskIds.slice(start, start + BULK_CHUNK_SIZE), action, params, confirm);
      succeeded += result.succeeded;
      failedTaskIds.push(...result.results.filter((item) => !item.success).map((item) => item.task_id));
    } catch {
      if (start === 0) {
        toast.error(t('updateError'));
        return null;
      }
      failedTaskIds.push(...taskIds.slice(start));
      break;
    }
  }

  if (failedTaskIds.length > 0) {
    toast.warning(t('bulkPartialSuccess', { succeeded, failed: failedTaskIds.length }));
  } else {
    toast.success(t('bulkSuccess', { count: succeeded }));
  }
  return failedTaskIds;
}
