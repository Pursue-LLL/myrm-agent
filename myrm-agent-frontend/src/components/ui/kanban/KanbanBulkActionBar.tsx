'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { X, Archive, ArrowRight, UserRound, Trash2 } from 'lucide-react';
import type { TaskStatus, BulkAction } from '@/services/kanban';
import { bulkAction } from '@/services/kanban';

interface KanbanBulkActionBarProps {
  boardId: string;
  selectedIds: string[];
  onClear: () => void;
  onComplete: () => void;
  agents: { id: string; name: string }[];
}

const MOVE_TARGETS: TaskStatus[] = ['ready', 'blocked', 'completed'];

export default function KanbanBulkActionBar({
  boardId,
  selectedIds,
  onClear,
  onComplete,
  agents,
}: KanbanBulkActionBarProps) {
  const t = useTranslations('kanban');
  const [loading, setLoading] = useState(false);
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const [showAssignMenu, setShowAssignMenu] = useState(false);
  const [showConfirmDelete, setShowConfirmDelete] = useState(false);

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
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
      setShowMoveMenu(false);
      setShowAssignMenu(false);
      setShowConfirmDelete(false);
    }
  };

  if (selectedIds.length === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 fade-in duration-200 max-w-[calc(100vw-2rem)]">
      <div className="flex items-center gap-2 px-3 sm:px-4 py-2.5 rounded-xl border bg-background/95 backdrop-blur-sm shadow-lg overflow-x-auto">
        <span className="text-sm font-medium tabular-nums">{t('bulkSelected', { count: selectedIds.length })}</span>

        <div className="w-px h-5 bg-border mx-1" />

        {/* Archive */}
        <button
          onClick={() => execute('archive')}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md hover:bg-muted transition-colors disabled:opacity-50"
          title={t('bulkArchive')}
        >
          <Archive className="w-3.5 h-3.5" />
          {t('bulkArchive')}
        </button>

        {/* Move status */}
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
              {MOVE_TARGETS.map((s) => (
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
          {showConfirmDelete ? (
            <div className="flex items-center gap-1">
              <span className="text-xs text-destructive">{t('bulkDeleteConfirm', { count: selectedIds.length })}</span>
              <button
                onClick={() => execute('delete', {}, true)}
                disabled={loading}
                className="text-xs px-2 py-1 rounded bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {t('confirm')}
              </button>
              <button
                onClick={() => setShowConfirmDelete(false)}
                className="text-xs px-2 py-1 rounded hover:bg-muted transition-colors"
              >
                {t('cancel')}
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowConfirmDelete(true)}
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
