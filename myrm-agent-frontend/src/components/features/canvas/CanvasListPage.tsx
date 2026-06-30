/**
 * [INPUT]
 * - @/store/useCanvasStore (POS: Canvas 状态)
 * - next-intl (POS: i18n — useTranslations)
 * - lucide-react (POS: Icon library)
 * - @/components/primitives/alert-dialog (POS: shadcn AlertDialog)
 *
 * [OUTPUT]
 * - CanvasListPage: React component — canvas list with create/rename/delete
 *
 * [POS]
 * Canvas list view. Shows all canvases with thumbnails (if available),
 * supports create, rename, and delete. Clicking a canvas navigates to
 * the editor page.
 */

'use client';

import { PenTool, Plus, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { useCanvasStore } from '@/store/useCanvasStore';

export default function CanvasListPage() {
  const t = useTranslations('canvas');
  const router = useRouter();
  const { canvases, loading, fetchCanvases, createCanvas, renameCanvas, removeCanvas } =
    useCanvasStore();
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  useEffect(() => {
    fetchCanvases();
  }, [fetchCanvases]);

  const handleCreate = useCallback(async () => {
    const canvas = await createCanvas();
    router.push(`/canvas/${canvas.id}`);
  }, [createCanvas, router]);

  const handleOpen = useCallback(
    (id: string) => {
      router.push(`/canvas/${id}`);
    },
    [router],
  );

  const handleRenameStart = useCallback((id: string, currentName: string) => {
    setRenamingId(id);
    setRenameValue(currentName);
  }, []);

  const handleRenameConfirm = useCallback(async () => {
    if (renamingId && renameValue.trim()) {
      await renameCanvas(renamingId, renameValue.trim());
    }
    setRenamingId(null);
    setRenameValue('');
  }, [renamingId, renameValue, renameCanvas]);

  const handleDeleteClick = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteTarget(id);
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    if (deleteTarget) {
      await removeCanvas(deleteTarget);
      setDeleteTarget(null);
    }
  }, [deleteTarget, removeCanvas]);

  if (loading && canvases.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        {t('loading')}
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl sm:text-2xl font-semibold text-foreground">{t('title')}</h1>
        <button
          onClick={handleCreate}
          className="flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
        >
          <Plus size={16} />
          <span className="hidden sm:inline">{t('newCanvas')}</span>
        </button>
      </div>

      {/* Empty state */}
      {canvases.length === 0 ? (
        <div className="text-center py-16 px-5 text-muted-foreground">
          <PenTool size={40} className="mx-auto mb-4 opacity-30" />
          <p className="text-base mb-2">{t('emptyTitle')}</p>
          <p className="text-sm">{t('emptyDescription')}</p>
        </div>
      ) : (
        /* Canvas grid */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {canvases.map((canvas) => (
            <div
              key={canvas.id}
              onClick={() => handleOpen(canvas.id)}
              className="group border border-border rounded-xl overflow-hidden cursor-pointer bg-card transition-all duration-200 hover:shadow-md hover:border-primary/50"
            >
              {/* Thumbnail area */}
              <div className="h-32 sm:h-36 bg-gradient-to-br from-accent to-muted flex items-center justify-center">
                {canvas.thumbnail ? (
                  <img
                    src={canvas.thumbnail}
                    alt={canvas.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <PenTool size={28} className="text-muted-foreground/30" />
                )}
              </div>

              {/* Info area */}
              <div className="px-3 py-2.5 sm:px-4 sm:py-3">
                {renamingId === canvas.id ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={handleRenameConfirm}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRenameConfirm();
                      if (e.key === 'Escape') setRenamingId(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="w-full border border-primary rounded px-2 py-1 text-sm outline-none bg-background text-foreground"
                  />
                ) : (
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className="text-sm font-medium text-foreground truncate flex-1"
                      onDoubleClick={(e) => {
                        e.stopPropagation();
                        handleRenameStart(canvas.id, canvas.name);
                      }}
                    >
                      {canvas.name}
                    </span>
                    <button
                      onClick={(e) => handleDeleteClick(canvas.id, e)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded text-muted-foreground hover:text-destructive transition-all shrink-0"
                      title={t('deleteTitle')}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
                <div className="text-xs text-muted-foreground mt-1">
                  {canvas.updated_at
                    ? new Date(canvas.updated_at).toLocaleDateString()
                    : t('justCreated')}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete confirmation dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
