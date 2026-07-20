'use client';

import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import type { KanbanBoard, BoardSummary } from '@/services/kanban';
import { listBoards, createBoard, deleteBoard, updateBoard, getBoardSummary } from '@/services/kanban';
import { writeKanbanLastBoardId, readKanbanLastBoardId } from '@/lib/kanban/kanbanChatBoard';
import KanbanBoardView from '@/components/features/kanban/KanbanBoardView';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { registerSettingsSubviewBack } from '@/components/features/settings/settingsSubviewBack';

export default function KanbanSection() {
  const t = useTranslations('kanban');
  const searchParams = useSearchParams();
  const sourceChatParam = searchParams.get('source_chat')?.trim() || undefined;
  const boardIdParam = searchParams.get('board_id')?.trim() || undefined;
  const [boards, setBoards] = useState<KanbanBoard[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedBoard, setSelectedBoard] = useState<KanbanBoard | null>(null);
  const selectBoard = useCallback((board: KanbanBoard | null) => {
    setSelectedBoard(board);
    writeKanbanLastBoardId(board?.board_id ?? null);
  }, []);
  const [showCreate, setShowCreate] = useState(false);
  const [newBoardName, setNewBoardName] = useState('');
  const [newBoardDesc, setNewBoardDesc] = useState('');
  const [newBoardWorkdir, setNewBoardWorkdir] = useState('');
  const [editingBoard, setEditingBoard] = useState<KanbanBoard | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editMaxConcurrent, setEditMaxConcurrent] = useState(3);
  const [editDefaultWorkdir, setEditDefaultWorkdir] = useState('');
  const [deletingBoard, setDeletingBoard] = useState<KanbanBoard | null>(null);
  const [deleteSummary, setDeleteSummary] = useState<BoardSummary | null>(null);

  const fetchBoards = useCallback(async () => {
    try {
      const result = await listBoards();
      setBoards(result.items);
    } catch {
      toast.error(t('fetchBoardsError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchBoards();
  }, [fetchBoards]);

  useEffect(() => {
    if (loading || selectedBoard || boards.length === 0) return;

    if (boardIdParam) {
      const match = boards.find((b) => b.board_id === boardIdParam);
      if (match) {
        selectBoard(match);
        return;
      }
    }

    if (sourceChatParam) {
      if (boards.length === 1) {
        selectBoard(boards[0]!);
        return;
      }
      const lastId = readKanbanLastBoardId();
      if (lastId) {
        const match = boards.find((b) => b.board_id === lastId);
        if (match) {
          selectBoard(match);
          return;
        }
      }
    }

    const lastId = readKanbanLastBoardId();
    if (!lastId) return;
    const match = boards.find((b) => b.board_id === lastId);
    if (match) selectBoard(match);
    else writeKanbanLastBoardId(null);
  }, [loading, boards, selectedBoard, boardIdParam, sourceChatParam, selectBoard]);

  useEffect(() => {
    if (!selectedBoard) {
      registerSettingsSubviewBack(null);
      return;
    }
    registerSettingsSubviewBack(() => {
      selectBoard(null);
      return true;
    });
    return () => registerSettingsSubviewBack(null);
  }, [selectedBoard, selectBoard]);

  const handleCreate = useCallback(async () => {
    if (!newBoardName.trim()) return;
    const createdName = newBoardName.trim();
    try {
      await createBoard({
        name: createdName,
        description: newBoardDesc.trim(),
        ...(newBoardWorkdir.trim() ? { default_workdir: newBoardWorkdir.trim() } : {}),
      });
      setNewBoardName('');
      setNewBoardDesc('');
      setNewBoardWorkdir('');
      setShowCreate(false);
      const refreshed = await listBoards();
      const createdBoard = refreshed.items.find((b) => b.name === createdName);
      if (createdBoard) {
        writeKanbanLastBoardId(createdBoard.board_id);
      }
      await fetchBoards();
      toast.success(t('boardCreated'));
    } catch {
      toast.error(t('createBoardError'));
    }
  }, [newBoardName, newBoardDesc, newBoardWorkdir, fetchBoards, t]);

  const handleDeleteConfirm = useCallback(async () => {
    if (!deletingBoard) return;
    try {
      await deleteBoard(deletingBoard.board_id);
      if (readKanbanLastBoardId() === deletingBoard.board_id) {
        writeKanbanLastBoardId(null);
      }
      await fetchBoards();
      if (selectedBoard?.board_id === deletingBoard.board_id) {
        selectBoard(null);
      }
      toast.success(t('boardDeleted'));
    } catch {
      toast.error(t('deleteBoardError'));
    }
  }, [deletingBoard, fetchBoards, selectedBoard, selectBoard, t]);

  const startDelete = useCallback(async (board: KanbanBoard) => {
    setDeletingBoard(board);
    setDeleteSummary(null);
    try {
      const summary = await getBoardSummary(board.board_id);
      setDeleteSummary(summary);
    } catch {
      // Summary fetch failed; dialog still works with static text
    }
  }, []);

  const deleteDescription = useCallback(() => {
    const name = deletingBoard?.name ?? '';
    if (!deleteSummary || deleteSummary.total_tasks === 0) {
      return t('deleteBoardConfirmDesc', { name });
    }
    const running = deleteSummary.task_counts['running'] ?? 0;
    if (running > 0) {
      return t('deleteBoardConfirmDescRunning', {
        name,
        total: deleteSummary.total_tasks,
        running,
      });
    }
    return t('deleteBoardConfirmDescWithTasks', {
      name,
      total: deleteSummary.total_tasks,
    });
  }, [deletingBoard, deleteSummary, t]);

  const startEdit = useCallback((board: KanbanBoard, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingBoard(board);
    setEditName(board.name);
    setEditDesc(board.description);
    setEditMaxConcurrent(board.settings.max_concurrent_tasks);
    setEditDefaultWorkdir(board.settings.default_workdir ?? '');
  }, []);

  const handleUpdate = useCallback(async () => {
    if (!editingBoard || !editName.trim()) return;
    try {
      await updateBoard(editingBoard.board_id, {
        name: editName.trim(),
        description: editDesc.trim(),
        max_concurrent_tasks: editMaxConcurrent,
        default_workdir: editDefaultWorkdir.trim() || null,
      });
      setEditingBoard(null);
      await fetchBoards();
      toast.success(t('boardUpdated'));
    } catch {
      toast.error(t('updateBoardError'));
    }
  }, [editingBoard, editName, editDesc, editMaxConcurrent, editDefaultWorkdir, fetchBoards, t]);

  if (selectedBoard) {
    return <KanbanBoardView board={selectedBoard} onBack={() => selectBoard(null)} />;
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="w-5 h-5 rounded bg-primary/10 text-primary flex items-center justify-center text-xs font-bold">
            K
          </span>
          <h2 className="text-base font-semibold">{t('sectionTitle')}</h2>
        </div>
        <p className="text-sm text-muted-foreground">{t('sectionDesc')}</p>
      </div>

      {/* Board list */}
      {loading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-16 rounded-lg bg-muted/30 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {boards.map((board) =>
            editingBoard?.board_id === board.board_id ? (
              <div key={board.board_id} className="space-y-2 p-3 rounded-lg border bg-muted/20">
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder={t('boardNamePlaceholder')}
                  className="w-full text-sm px-3 py-2 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  autoFocus
                />
                <input
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  placeholder={t('boardDescPlaceholder')}
                  className="w-full text-sm px-3 py-2 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <div className="flex items-center gap-2">
                  <label className="text-xs text-muted-foreground whitespace-nowrap">{t('maxConcurrentTasks')}</label>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={editMaxConcurrent}
                    onChange={(e) => setEditMaxConcurrent(Number(e.target.value))}
                    className="w-20 text-sm px-3 py-2 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-muted-foreground whitespace-nowrap">{t('defaultWorkdir')}</label>
                  <input
                    value={editDefaultWorkdir}
                    onChange={(e) => setEditDefaultWorkdir(e.target.value)}
                    placeholder={t('defaultWorkdirPlaceholder')}
                    className="flex-1 text-sm px-3 py-2 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleUpdate}
                    className="text-sm px-3 py-1.5 rounded bg-primary text-primary-foreground hover:bg-primary/90"
                  >
                    {t('save')}
                  </button>
                  <button onClick={() => setEditingBoard(null)} className="text-sm px-3 py-1.5 rounded hover:bg-muted">
                    {t('cancel')}
                  </button>
                </div>
              </div>
            ) : (
              <div
                key={board.board_id}
                role="button"
                tabIndex={0}
                data-testid={`kanban-board-row-${board.board_id}`}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  selectBoard(board);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    selectBoard(board);
                  }
                }}
                className="group flex items-center justify-between p-3 rounded-lg border hover:border-primary/30 hover:bg-primary/5 cursor-pointer transition-colors"
              >
                <div>
                  <h3 className="text-sm font-medium">{board.name}</h3>
                  {board.description && <p className="text-xs text-muted-foreground mt-0.5">{board.description}</p>}
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                  <button
                    onClick={(e) => startEdit(board, e)}
                    className="text-xs px-1.5 py-0.5 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                  >
                    {t('edit')}
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startDelete(board);
                    }}
                    className="text-xs px-1.5 py-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                  >
                    &times;
                  </button>
                </div>
              </div>
            ),
          )}

          {boards.length === 0 && !showCreate && (
            <div className="flex flex-col items-center text-center py-6 gap-3">
              <p className="text-sm text-muted-foreground">{t('noBoards')}</p>
              <button
                type="button"
                onClick={() => setShowCreate(true)}
                className="text-sm px-3 py-1.5 rounded bg-primary text-primary-foreground hover:bg-primary/90"
              >
                + {t('createBoard')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Create board form */}
      {showCreate ? (
        <div className="space-y-2 p-3 rounded-lg border bg-muted/20">
          <input
            value={newBoardName}
            onChange={(e) => setNewBoardName(e.target.value)}
            placeholder={t('boardNamePlaceholder')}
            className="w-full text-sm px-3 py-2 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            autoFocus
          />
          <input
            value={newBoardDesc}
            onChange={(e) => setNewBoardDesc(e.target.value)}
            placeholder={t('boardDescPlaceholder')}
            className="w-full text-sm px-3 py-2 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground whitespace-nowrap">{t('defaultWorkdir')}</label>
            <input
              value={newBoardWorkdir}
              onChange={(e) => setNewBoardWorkdir(e.target.value)}
              placeholder={t('defaultWorkdirPlaceholder')}
              className="flex-1 text-sm px-3 py-2 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              className="text-sm px-3 py-1.5 rounded bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {t('create')}
            </button>
            <button
              onClick={() => {
                setShowCreate(false);
                setNewBoardName('');
                setNewBoardDesc('');
                setNewBoardWorkdir('');
              }}
              className="text-sm px-3 py-1.5 rounded hover:bg-muted"
            >
              {t('cancel')}
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          + {t('createBoard')}
        </button>
      )}

      <ConfirmDialog
        open={!!deletingBoard}
        onOpenChange={(open) => {
          if (!open) {
            setDeletingBoard(null);
            setDeleteSummary(null);
          }
        }}
        title={t('deleteBoardConfirmTitle')}
        description={deleteDescription()}
        confirmText={t('delete')}
        cancelText={t('cancel')}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
}
