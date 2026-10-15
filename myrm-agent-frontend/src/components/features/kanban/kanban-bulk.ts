/**
 * [INPUT]
 * - @/services/kanban::bulkAction, BulkAction (POS: 看板批量接口客户端)
 * - sonner::toast (POS: 结果提示)
 *
 * [OUTPUT]
 * - runBulkAction: 发起批量请求并汇总提示，返回未成功的任务 id
 *
 * [POS]
 * 批量工具栏与批量拖拽共用的执行入口，两条路径因此有同一套结果语义：批量请求允许部分成功，
 * 成功与部分失败各给一条汇总提示，逐条的服务端错误原文不透出；失败的任务 id 交还调用方，
 * 由它让这些任务继续保持选中以便原地重试。
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
 * 返回未成功的任务 id；整个请求失败（网络、服务端异常）时已提示本地化错误并返回 `null`，
 * 此时没有任何任务被确认处理，调用方应当回滚乐观更新。
 */
export async function runBulkAction({
  boardId,
  taskIds,
  action,
  params = {},
  confirm = false,
  t,
}: RunBulkActionOptions): Promise<string[] | null> {
  try {
    const result = await bulkAction(boardId, taskIds, action, params, confirm);
    if (result.failed > 0) {
      toast.warning(t('bulkPartialSuccess', { succeeded: result.succeeded, failed: result.failed }));
    } else {
      toast.success(t('bulkSuccess', { count: result.succeeded }));
    }
    return result.results.filter((item) => !item.success).map((item) => item.task_id);
  } catch {
    toast.error(t('updateError'));
    return null;
  }
}
