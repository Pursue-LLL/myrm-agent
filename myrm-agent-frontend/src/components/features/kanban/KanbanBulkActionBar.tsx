'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { X, Archive, ArrowRight, UserRound, Trash2 } from 'lucide-react';
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

/** 归档后任务离开看板、删除不可恢复：两者都先在原位置二次确认。 */
type PendingConfirm = 'archive' | 'delete';

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
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const [showAssignMenu, setShowAssignMenu] = useState(false);
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
      setShowMoveMenu(false);
      setShowAssignMenu(false);
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
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 fade-in duration-200 max-w-[calc(100vw-2rem)]">
      <div className="flex items-center gap-2 px-3 sm:px-4 py-2.5 rounded-xl border bg-background/95 backdrop-blur-sm shadow-lg overflow-x-auto whitespace-nowrap [&>*]:shrink-0">
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
          <button
            onClick={() => setPendingConfirm('archive')}
            disabled={loading}
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md hover:bg-muted transition-colors disabled:opacity-50"
            title={t('bulkArchive')}
          >
            <Archive className="w-3.5 h-3.5" />
            {t('bulkArchive')}
          </button>
        )}

        {/* Move status */}
        {moveTargets.length > 0 && (
          <div className="relative">
            <button
              onClick={() => {
                setShowMoveMenu((v) => !v);
                setShowAssignMenu(false);
              }}
              disabled={loading}
              className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md hover:bg-muted transition-colors disabled:opacity-50"
            >
              <ArrowRight className="w-3.5 h-3.5" />
              {t('bulkMove')}
            </button>
            {showMoveMenu && (
              <div className="absolute bottom-full mb-1 left-0 bg-popover border rounded-md shadow-md py-1 min-w-[120px]">
                {moveTargets.map((s) => (
                  <button
                    key={s}
                    onClick={() => execute('move', { status: s })}
                    className="w-full text-left text-xs px-3 py-1.5 hover:bg-muted transition-colors"
                  >
                    {t(`status.${s}`)}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Reassign */}
        <div className="relative">
          <button
            onClick={() => {
              setShowAssignMenu((v) => !v);
              setShowMoveMenu(false);
            }}
            disabled={loading}
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md hover:bg-muted transition-colors disabled:opacity-50"
          >
            <UserRound className="w-3.5 h-3.5" />
            {t('bulkReassign')}
          </button>
          {showAssignMenu && (
            <div className="absolute bottom-full mb-1 left-0 bg-popover border rounded-md shadow-md py-1 min-w-[140px] max-h-[200px] overflow-y-auto">
              <button
                onClick={() => execute('reassign', { agent_id: '' })}
                className="w-full text-left text-xs px-3 py-1.5 hover:bg-muted transition-colors italic text-muted-foreground"
              >
                {t('unassigned')}
              </button>
              {agents.map((ag) => (
                <button
                  key={ag.id}
                  onClick={() => execute('reassign', { agent_id: ag.id })}
                  className="w-full text-left text-xs px-3 py-1.5 hover:bg-muted transition-colors truncate"
                >
                  {ag.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Delete */}
        <div className="relative">
          {pendingConfirm === 'delete' ? (
            <InlineConfirm
              message={t('bulkDeleteConfirm', { count: selectedIds.length })}
              tone="destructive"
              loading={loading}
              onConfirm={() => execute('delete', {}, true)}
              onCancel={() => setPendingConfirm(null)}
            />
          ) : (
            <button
              onClick={() => setPendingConfirm('delete')}
              disabled={loading}
              className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md hover:bg-destructive/10 text-destructive transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              {t('bulkDelete')}
            </button>
          )}
        </div>

        <div className="w-px h-5 bg-border mx-1" />

        {/* Clear selection */}
        <button
          onClick={onClear}
          className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          title={t('bulkClearSelection')}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
