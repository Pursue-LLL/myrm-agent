/**
 * [INPUT]
 * - @/components/primitives/dropdown-menu (POS: Radix 下拉菜单封装，内容经 portal 渲染)
 * - ./kanban-transitions::isServerMoveAllowed (POS: 看板状态流转判定，服务端 move 守卫的镜像)
 * - @/services/kanban::bulkAction, BulkAction, TaskStatus (POS: 看板 API 请求与类型)
 *
 * [OUTPUT]
 * - KanbanBulkActionBar (default): 多选任务后的批量移动 / 归档 / 重新分配 / 删除工具栏
 *
 * [POS]
 * 看板多选后的批量操作入口。「移至」只列出至少对一个选中任务可达的目标；归档与删除在原位二次确认；
 * 批量请求允许部分成功，结果以 toast 汇总。两个下拉菜单走 portal，不受浮条自身布局裁剪；窄屏只显示图标并允许换行。
 */
'use client';

import { useState, type ComponentProps, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { X, Archive, ArrowRight, UserRound, Trash2 } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import { cn } from '@/lib/utils/classnameUtils';
import type { TaskStatus, BulkAction } from '@/services/kanban';
import { bulkAction } from '@/services/kanban';
import { isServerMoveAllowed } from './kanban-transitions';

interface KanbanBulkActionBarProps {
  boardId: string;
  selectedIds: string[];
  /** 选中任务当前的状态；为空（查不到任务）时不过滤移动目标。 */
  selectedStatuses: TaskStatus[];
  onClear: () => void;
  onComplete: () => void;
  agents: { id: string; name: string }[];
}

const MOVE_TARGETS: TaskStatus[] = ['ready', 'blocked', 'completed'];

const BAR_BUTTON_CLASS =
  'inline-flex items-center gap-1.5 text-xs px-2 sm:px-2.5 py-1.5 rounded-md hover:bg-muted transition-colors disabled:opacity-50';
const MENU_ITEM_CLASS = 'pointer-coarse:min-h-11';

/** 归档后任务离开看板、删除不可恢复：两者都先在原位置二次确认。 */
type PendingConfirm = 'archive' | 'delete';

interface BarButtonProps extends ComponentProps<'button'> {
  icon: ReactNode;
  label: string;
}

/** 窄屏只留图标，文字退为 aria-label；ref 与事件属性透传，可直接作为菜单触发器。 */
function BarButton({ icon, label, className, ...props }: BarButtonProps) {
  return (
    <button type="button" aria-label={label} className={cn(BAR_BUTTON_CLASS, className)} {...props}>
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

interface InlineConfirmProps {
  message: string;
  tone: 'default' | 'destructive';
  loading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

function InlineConfirm({ message, tone, loading, onConfirm, onCancel }: InlineConfirmProps) {
  const t = useTranslations('kanban');
  const destructive = tone === 'destructive';
  return (
    <div className="flex items-center gap-1">
      <span className={cn('text-xs', destructive && 'text-destructive')}>{message}</span>
      <button
        onClick={onConfirm}
        disabled={loading}
        className={cn(
          'text-xs px-2 py-1 rounded transition-colors disabled:opacity-50',
          destructive
            ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
            : 'bg-primary text-primary-foreground hover:bg-primary/90',
        )}
      >
        {t('confirm')}
      </button>
      <button onClick={onCancel} className="text-xs px-2 py-1 rounded hover:bg-muted transition-colors">
        {t('cancel')}
      </button>
    </div>
  );
}

export default function KanbanBulkActionBar({
  boardId,
  selectedIds,
  selectedStatuses,
  onClear,
  onComplete,
  agents,
}: KanbanBulkActionBarProps) {
  const t = useTranslations('kanban');
  const [loading, setLoading] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);

  const execute = async (action: BulkAction, params: Record<string, string> = {}, confirm = false) => {
    setLoading(true);
    try {
      const result = await bulkAction(boardId, selectedIds, action, params, confirm);
      if (result.failed > 0) {
        toast.warning(t('bulkPartialSuccess', { succeeded: result.succeeded, failed: result.failed }));
      } else {
        toast.success(t('bulkSuccess', { count: result.succeeded }));
      }
      onClear();
      onComplete();
    } catch {
      toast.error(t('updateError'));
    } finally {
      setLoading(false);
      setPendingConfirm(null);
    }
  };

  if (selectedIds.length === 0) {
    return null;
  }

  // 只隐藏对整个选择必然全部失败的目标；仍有任务能到达的目标保留，混合选择由服务端逐条返回部分成功。
  const moveTargets =
    selectedStatuses.length === 0
      ? MOVE_TARGETS
      : MOVE_TARGETS.filter((to) => selectedStatuses.some((from) => isServerMoveAllowed(from, to)));

  return (
    // 底部 bottom-6 一行已被全局悬浮入口（Workbench / Session Map / Designer Eye）占用，浮条抬到它们之上。
    <div
      data-testid="kanban-bulk-bar"
      className="fixed inset-x-0 bottom-[4.5rem] mx-auto w-fit max-w-[calc(100vw-2rem)] z-50 animate-in slide-in-from-bottom-4 fade-in duration-200"
    >
      <div className="flex flex-wrap items-center justify-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2.5 rounded-xl border bg-background/95 backdrop-blur-sm shadow-lg whitespace-nowrap">
        <span className="text-sm font-medium tabular-nums">{t('bulkSelected', { count: selectedIds.length })}</span>

        <div className="w-px h-5 bg-border mx-1" />

        {/* Archive */}
        {pendingConfirm === 'archive' ? (
          <InlineConfirm
            message={t('bulkArchiveConfirm', { count: selectedIds.length })}
            tone="default"
            loading={loading}
            onConfirm={() => execute('archive')}
            onCancel={() => setPendingConfirm(null)}
          />
        ) : (
          <BarButton
            onClick={() => setPendingConfirm('archive')}
            disabled={loading}
            icon={<Archive className="w-3.5 h-3.5" />}
            label={t('bulkArchive')}
          />
        )}

        {/* Move status */}
        {moveTargets.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <BarButton disabled={loading} icon={<ArrowRight className="w-3.5 h-3.5" />} label={t('bulkMove')} />
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start">
              {moveTargets.map((status) => (
                <DropdownMenuItem key={status} className={MENU_ITEM_CLASS} onSelect={() => execute('move', { status })}>
                  {t(`status.${status}`)}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {/* Reassign */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <BarButton disabled={loading} icon={<UserRound className="w-3.5 h-3.5" />} label={t('bulkReassign')} />
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start">
            <DropdownMenuItem
              className={cn(MENU_ITEM_CLASS, 'italic text-muted-foreground')}
              onSelect={() => execute('reassign', { agent_id: '' })}
            >
              {t('unassigned')}
            </DropdownMenuItem>
            {agents.map((agent) => (
              <DropdownMenuItem
                key={agent.id}
                className={MENU_ITEM_CLASS}
                onSelect={() => execute('reassign', { agent_id: agent.id })}
              >
                <span className="truncate">{agent.name}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Delete */}
        {pendingConfirm === 'delete' ? (
          <InlineConfirm
            message={t('bulkDeleteConfirm', { count: selectedIds.length })}
            tone="destructive"
            loading={loading}
            onConfirm={() => execute('delete', {}, true)}
            onCancel={() => setPendingConfirm(null)}
          />
        ) : (
          <BarButton
            onClick={() => setPendingConfirm('delete')}
            disabled={loading}
            className="text-destructive hover:bg-destructive/10"
            icon={<Trash2 className="w-3.5 h-3.5" />}
            label={t('bulkDelete')}
          />
        )}

        <div className="w-px h-5 bg-border mx-1" />

        {/* Clear selection */}
        <button
          type="button"
          onClick={onClear}
          aria-label={t('bulkClearSelection')}
          title={t('bulkClearSelection')}
          className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
