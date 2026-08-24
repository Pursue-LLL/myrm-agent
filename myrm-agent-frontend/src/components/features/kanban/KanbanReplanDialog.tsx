'use client';

/**
 * KanbanReplanDialog — Board Plan Revision Review & Apply Modal.
 *
 * [INPUT]
 * - @/services/kanban::reviseBoardPlan, PlanRevisionRequest, PlanRevisionItem
 *
 * [OUTPUT]
 * - Default export <KanbanReplanDialog /> — controlled modal.
 *
 * [POS]
 * Visual Diff modal for formal DAG plan revisions. Allows review of added,
 * updated, and removed tasks/edges with invariant checks before atomic commit.
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { GitCompare, Plus, RefreshCw, Trash2, ShieldCheck, AlertCircle } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import type { KanbanBoard, PlanRevisionItem } from '@/services/kanban';
import { reviseBoardPlan } from '@/services/kanban';

interface KanbanReplanDialogProps {
  board: KanbanBoard | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  proposedChanges: PlanRevisionItem[];
  proposedAddEdges?: [string, string][];
  proposedRemoveEdges?: [string, string][];
  defaultRationale?: string;
  onApplied?: () => void;
}

export default function KanbanReplanDialog({
  board,
  open,
  onOpenChange,
  proposedChanges,
  proposedAddEdges = [],
  proposedRemoveEdges = [],
  defaultRationale = '',
  onApplied,
}: KanbanReplanDialogProps) {
  const t = useTranslations('kanban');
  const [rationale, setRationale] = useState(defaultRationale);
  const [applying, setApplying] = useState(false);

  const addedTasks = proposedChanges.filter((c) => c.action === 'add');
  const updatedTasks = proposedChanges.filter((c) => c.action === 'update');
  const removedTasks = proposedChanges.filter((c) => c.action === 'remove');

  const handleApply = async () => {
    if (!board) return;
    if (!rationale.trim()) {
      toast.error(t('replanRationaleRequired') || 'Rationale is required for plan revision');
      return;
    }

    setApplying(true);
    try {
      const result = await reviseBoardPlan(board.board_id, {
        board_id: board.board_id,
        rationale: rationale.trim(),
        task_changes: proposedChanges,
        add_edges: proposedAddEdges,
        remove_edges: proposedRemoveEdges,
        author: 'user',
      });

      if (result.ok) {
        toast.success(t('replanAppliedSuccess') || 'Plan revision applied successfully');
        onOpenChange(false);
        onApplied?.();
      } else {
        toast.error(result.reason || t('replanFailed') || 'Plan revision failed');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg || t('replanFailed') || 'Plan revision error');
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-6">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base font-semibold">
            <GitCompare className="w-5 h-5 text-primary" />
            {t('replanTitle') || 'DAG Plan Revision Review'}
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            {t('replanDescription') ||
              'Review proposed modifications to the task graph. All changes will be validated for acyclicity and applied atomically.'}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 py-2 pr-1">
          {/* Summary Badges */}
          <div className="grid grid-cols-3 gap-2">
            <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400">
              <Plus className="w-4 h-4" />
              <div className="text-xs">
                <span className="font-semibold">{addedTasks.length}</span> {t('replanAdded') || 'Tasks to Add'}
              </div>
            </div>
            <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400">
              <RefreshCw className="w-4 h-4" />
              <div className="text-xs">
                <span className="font-semibold">{updatedTasks.length}</span> {t('replanUpdated') || 'Tasks to Update'}
              </div>
            </div>
            <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-rose-500/10 border-rose-500/20 text-rose-600 dark:text-rose-400">
              <Trash2 className="w-4 h-4" />
              <div className="text-xs">
                <span className="font-semibold">{removedTasks.length}</span> {t('replanRemoved') || 'Tasks to Remove'}
              </div>
            </div>
          </div>

          {/* Rationale Input */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">
              {t('replanRationaleLabel') || 'Revision Rationale / Trigger Reason'}
            </label>
            <input
              type="text"
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              placeholder={t('replanRationalePlaceholder') || 'e.g. Discovered missing API schema dependencies'}
              className="w-full px-3 py-1.5 text-xs rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          {/* Detailed Task Changes Diff */}
          <div className="space-y-2">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              {t('replanChangesList') || 'Detailed Diff Changes'}
            </div>
            <div className="space-y-2 max-h-60 overflow-y-auto border rounded-lg p-2 bg-muted/20">
              {proposedChanges.length === 0 ? (
                <div className="text-xs text-muted-foreground text-center py-4">
                  {t('replanNoChanges') || 'No task modifications proposed'}
                </div>
              ) : (
                proposedChanges.map((change, idx) => (
                  <div key={idx} className="flex items-start gap-2 p-2 rounded border bg-background text-xs">
                    {change.action === 'add' && (
                      <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
                        ADD
                      </span>
                    )}
                    {change.action === 'update' && (
                      <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-amber-500/20 text-amber-600 dark:text-amber-400">
                        UPDATE
                      </span>
                    )}
                    {change.action === 'remove' && (
                      <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-rose-500/20 text-rose-600 dark:text-rose-400">
                        REMOVE
                      </span>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{change.title || change.task_id || 'Untitled'}</div>
                      {change.description && (
                        <div className="text-[11px] text-muted-foreground truncate">{change.description}</div>
                      )}
                      {change.depends_on && change.depends_on.length > 0 && (
                        <div className="text-[10px] text-muted-foreground mt-0.5">
                          Depends on: {change.depends_on.join(', ')}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Invariant Assurance Banner */}
          <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-blue-500/10 border-blue-500/20 text-blue-600 dark:text-blue-400 text-xs">
            <ShieldCheck className="w-4 h-4 shrink-0" />
            <div>
              {t('replanInvariantGuaranteed') ||
                'Completed and In-Review tasks are strictly locked and will not be altered. DAG acyclicity will be validated on commit.'}
            </div>
          </div>
        </div>

        <DialogFooter className="flex items-center justify-end gap-2 pt-3 border-t">
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={applying}
            className="px-3 py-1.5 text-xs font-medium rounded-md border hover:bg-muted transition-colors disabled:opacity-50"
          >
            {t('cancel') || 'Cancel'}
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={applying || proposedChanges.length === 0}
            className="px-4 py-1.5 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            {applying && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
            {t('replanApply') || 'Apply Plan Revision'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
