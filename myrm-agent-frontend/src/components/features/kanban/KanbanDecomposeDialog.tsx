'use client';

/**
 * KanbanDecomposeDialog — TRIAGE → child task graph preview / Apply UI.
 *
 * [INPUT]
 * - @/services/kanban::decomposeTask, applyDecompose
 *
 * [OUTPUT]
 * - Default export <KanbanDecomposeDialog /> — controlled modal.
 *
 * [POS]
 * Used by KanbanTaskCard to let users decompose a rough TRIAGE idea into
 * a graph of child tasks via the platform LLM. Shows a preview with
 * editable titles/assignees, then persists atomically on Apply.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { GitBranch, ArrowRight, Sparkles } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import type { DecomposeChildSpec, DecomposeOutcome, KanbanTask } from '@/services/kanban';
import { applyDecompose, decomposeTask } from '@/services/kanban';

interface KanbanDecomposeDialogProps {
  task: KanbanTask | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApplied?: () => void;
}

export default function KanbanDecomposeDialog({ task, open, onOpenChange, onApplied }: KanbanDecomposeDialogProps) {
  const t = useTranslations('kanban');
  const [outcome, setOutcome] = useState<DecomposeOutcome | null>(null);
  const [editableChildren, setEditableChildren] = useState<DecomposeChildSpec[]>([]);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const runPreview = useCallback(
    async (taskId: string) => {
      setLoading(true);
      setOutcome(null);
      setEditableChildren([]);
      try {
        const result = await decomposeTask(taskId);
        setOutcome(result);
        if (result.ok && result.fanout) {
          setEditableChildren(result.children.map((c) => ({ ...c })));
        }
        if (!result.ok) {
          toast.error(t('decomposeFailed', { reason: result.reason || '' }));
        }
      } catch {
        toast.error(t('decomposeError'));
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (!open || !task) return;
    runPreview(task.task_id);
  }, [open, task, runPreview]);

  const handleApply = useCallback(async () => {
    if (!task || !outcome?.ok) return;
    if (outcome.fanout && editableChildren.length === 0) return;
    setApplying(true);
    try {
      const result = await applyDecompose(
        task.task_id,
        outcome.fanout
          ? {
              fanout: true,
              children: editableChildren,
              rationale: outcome.rationale,
              prompt_tokens: outcome.prompt_tokens,
              completion_tokens: outcome.completion_tokens,
            }
          : {
              fanout: false,
              new_title: outcome.new_title,
              new_body: outcome.new_body,
              new_assignee: outcome.new_assignee,
              rationale: outcome.rationale,
              prompt_tokens: outcome.prompt_tokens,
              completion_tokens: outcome.completion_tokens,
            },
      );
      if (result.ok && result.persisted) {
        toast.success(outcome.fanout ? t('decomposeApplied', { count: result.child_ids.length }) : t('specifyApplied'));
        onApplied?.();
        onOpenChange(false);
      } else {
        toast.error(t('decomposeFailed', { reason: result.reason || '' }));
      }
    } catch {
      toast.error(t('decomposeError'));
    } finally {
      setApplying(false);
    }
  }, [task, outcome, editableChildren, onApplied, onOpenChange, t]);

  const handleRegenerate = useCallback(() => {
    if (!task) return;
    runPreview(task.task_id);
  }, [task, runPreview]);

  const updateChildTitle = useCallback((idx: number, title: string) => {
    setEditableChildren((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], title };
      return next;
    });
  }, []);

  const updateChildAssignee = useCallback((idx: number, assignee: string) => {
    setEditableChildren((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], assignee: assignee || null };
      return next;
    });
  }, []);

  if (!task) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            {t('decomposeDialogTitle')}
          </DialogTitle>
          <DialogDescription>{t('decomposeDialogHint')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Original task */}
          <div>
            <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1">
              {t('originalIdea')}
            </h4>
            <div className="rounded border bg-muted/30 p-2 text-sm">
              <p className="font-medium">{task.title}</p>
              {task.description && (
                <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap break-words">{task.description}</p>
              )}
            </div>
          </div>

          {loading && (
            <div className="space-y-2">
              <div className="h-4 rounded bg-muted/40 animate-pulse" />
              <div className="h-20 rounded bg-muted/40 animate-pulse" />
              <div className="h-20 rounded bg-muted/40 animate-pulse" />
            </div>
          )}

          {/* No fanout — show spec preview */}
          {!loading && outcome?.ok && !outcome.fanout && (
            <div className="space-y-2">
              <div className="rounded border border-purple-500/30 bg-purple-500/5 p-3 text-sm">
                <p className="text-xs text-muted-foreground italic mb-2">{t('decomposeNoFanout')}</p>
                {outcome.rationale && <p className="text-xs text-muted-foreground mb-2">{outcome.rationale}</p>}
                {outcome.new_title && (
                  <div className="mb-1.5">
                    <h4 className="text-xs font-medium uppercase tracking-wider text-purple-600 dark:text-purple-400 mb-0.5">
                      {t('specifiedTitle')}
                    </h4>
                    <p className="font-medium break-words">{outcome.new_title}</p>
                  </div>
                )}
                {outcome.new_body && (
                  <div>
                    <h4 className="text-xs font-medium uppercase tracking-wider text-purple-600 dark:text-purple-400 mb-0.5">
                      {t('specifiedBody')}
                    </h4>
                    <pre className="text-xs whitespace-pre-wrap break-words font-sans max-h-60 overflow-y-auto">
                      {outcome.new_body}
                    </pre>
                  </div>
                )}
              </div>
              {(outcome.prompt_tokens != null || outcome.completion_tokens != null) && (
                <p className="text-[10px] text-muted-foreground italic">
                  {t('tokensUsed', {
                    prompt: outcome.prompt_tokens ?? 0,
                    completion: outcome.completion_tokens ?? 0,
                  })}
                </p>
              )}
            </div>
          )}

          {/* Fanout preview */}
          {!loading && outcome?.ok && outcome.fanout && editableChildren.length > 0 && (
            <>
              {outcome.rationale && <p className="text-xs text-muted-foreground italic">{outcome.rationale}</p>}
              <div className="space-y-2">
                {editableChildren.map((child, idx) => (
                  <div key={idx} className="rounded border border-blue-500/30 bg-blue-500/5 p-2 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-blue-600 dark:text-blue-400 shrink-0">T{idx}</span>
                      <input
                        type="text"
                        value={child.title}
                        onChange={(e) => updateChildTitle(idx, e.target.value)}
                        className="flex-1 text-sm font-medium bg-transparent border-b border-blue-500/20 focus:border-blue-500 outline-none px-1 py-0.5"
                      />
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{t('decomposeAssignee')}:</span>
                      <input
                        type="text"
                        value={child.assignee ?? ''}
                        onChange={(e) => updateChildAssignee(idx, e.target.value)}
                        placeholder={t('decomposeDefaultAssignee')}
                        className="bg-transparent border-b border-blue-500/20 focus:border-blue-500 outline-none px-1 py-0.5 w-32"
                      />
                      {child.parent_indices.length > 0 && (
                        <span className="inline-flex items-center gap-0.5 text-[10px] text-blue-600 dark:text-blue-400">
                          <ArrowRight className="w-2.5 h-2.5" />
                          {child.parent_indices.map((pi) => `T${pi}`).join(', ')}
                        </span>
                      )}
                    </div>
                    {child.body && (
                      <p className="text-xs text-muted-foreground whitespace-pre-wrap break-words line-clamp-3">
                        {child.body}
                      </p>
                    )}
                  </div>
                ))}
              </div>

              {(outcome.prompt_tokens != null || outcome.completion_tokens != null) && (
                <p className="text-[10px] text-muted-foreground italic">
                  {t('tokensUsed', {
                    prompt: outcome.prompt_tokens ?? 0,
                    completion: outcome.completion_tokens ?? 0,
                  })}
                </p>
              )}
            </>
          )}

          {/* Error state */}
          {!loading && outcome && !outcome.ok && (
            <div className="rounded border border-destructive/30 bg-destructive/5 p-2 text-sm text-destructive">
              {t('decomposeFailedDetail', { reason: outcome.reason || '' })}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2 flex-row flex-wrap justify-end">
          <button
            onClick={() => onOpenChange(false)}
            className="text-xs px-3 py-1.5 rounded border hover:bg-muted transition-colors"
          >
            {t('cancel')}
          </button>
          <button
            onClick={handleRegenerate}
            disabled={loading || applying}
            className="text-xs px-3 py-1.5 rounded border hover:bg-muted transition-colors disabled:opacity-50"
          >
            {t('regenerate')}
          </button>
          {outcome?.ok && outcome.fanout && (
            <button
              onClick={handleApply}
              disabled={loading || applying || editableChildren.length === 0}
              className="text-xs px-3 py-1.5 rounded bg-blue-500 text-white hover:bg-blue-600 transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              <GitBranch className="w-3 h-3" />
              {applying ? t('applying') : t('decomposeApply', { count: editableChildren.length })}
            </button>
          )}
          {outcome?.ok && !outcome.fanout && (outcome.new_title || outcome.new_body) && (
            <button
              onClick={handleApply}
              disabled={loading || applying}
              className="text-xs px-3 py-1.5 rounded bg-purple-500 text-white hover:bg-purple-600 transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              <Sparkles className="w-3 h-3" />
              {applying ? t('applying') : t('applyAndPromote')}
            </button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
