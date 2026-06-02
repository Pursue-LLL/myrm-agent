'use client';

/**
 * KanbanSpecifyDialog — TRIAGE → spec preview / Apply / Regenerate UI.
 *
 * [INPUT]
 * - @/services/kanban::specifyTask (POS: API client for the Specify endpoint.)
 *
 * [OUTPUT]
 * - Default export <KanbanSpecifyDialog /> — controlled modal.
 *
 * [POS]
 * Used by KanbanTaskCard / KanbanTaskDrawer to let users rewrite rough TRIAGE
 * ideas into actionable specs via the platform LLM. The first open triggers a
 * dry-run preview; users can Apply (persist + promote to READY) or Regenerate
 * (re-run dry-run) before committing.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { KanbanTask, SpecifyOutcome } from '@/services/kanban';
import { applySpec, specifyTask } from '@/services/kanban';

interface KanbanSpecifyDialogProps {
  task: KanbanTask | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApplied?: () => void;
}

export default function KanbanSpecifyDialog({ task, open, onOpenChange, onApplied }: KanbanSpecifyDialogProps) {
  const t = useTranslations('kanban');
  const [outcome, setOutcome] = useState<SpecifyOutcome | null>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const runPreview = useCallback(
    async (taskId: string) => {
      setLoading(true);
      setOutcome(null);
      try {
        const result = await specifyTask(taskId, { dryRun: true });
        setOutcome(result);
        if (!result.ok) {
          toast.error(t('specifyFailed', { reason: result.reason || '' }));
        }
      } catch {
        toast.error(t('specifyError'));
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
    if (!task || !outcome?.ok || !outcome.new_body) return;
    setApplying(true);
    try {
      const result = await applySpec(task.task_id, {
        new_title: outcome.new_title,
        new_body: outcome.new_body,
        prompt_tokens: outcome.prompt_tokens,
        completion_tokens: outcome.completion_tokens,
      });
      if (result.ok && result.persisted) {
        toast.success(t('specifyApplied'));
        onApplied?.();
        onOpenChange(false);
      } else {
        toast.error(t('specifyFailed', { reason: result.reason || '' }));
      }
    } catch {
      toast.error(t('specifyError'));
    } finally {
      setApplying(false);
    }
  }, [task, outcome, onApplied, onOpenChange, t]);

  const handleRegenerate = useCallback(() => {
    if (!task) return;
    runPreview(task.task_id);
  }, [task, runPreview]);

  if (!task) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            {t('specifyDialogTitle')}
          </DialogTitle>
          <DialogDescription>{t('specifyDialogHint')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
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
            </div>
          )}

          {!loading && outcome && outcome.ok && (
            <>
              <div>
                <h4 className="text-xs font-medium uppercase tracking-wider text-purple-600 dark:text-purple-400 mb-1">
                  {t('specifiedTitle')}
                </h4>
                <p className="rounded border border-purple-500/30 bg-purple-500/5 p-2 text-sm font-medium break-words">
                  {outcome.new_title ?? task.title}
                </p>
              </div>

              {outcome.new_body && (
                <div>
                  <h4 className="text-xs font-medium uppercase tracking-wider text-purple-600 dark:text-purple-400 mb-1">
                    {t('specifiedBody')}
                  </h4>
                  <pre className="rounded border border-purple-500/30 bg-purple-500/5 p-2 text-xs whitespace-pre-wrap break-words font-sans max-h-72 overflow-y-auto">
                    {outcome.new_body}
                  </pre>
                </div>
              )}

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

          {!loading && outcome && !outcome.ok && (
            <div className="rounded border border-destructive/30 bg-destructive/5 p-2 text-sm text-destructive">
              {t('specifyFailedDetail', { reason: outcome.reason || '' })}
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
          <button
            onClick={handleApply}
            disabled={loading || applying || !outcome?.ok}
            className="text-xs px-3 py-1.5 rounded bg-purple-500 text-white hover:bg-purple-600 transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            <Sparkles className="w-3 h-3" />
            {applying ? t('applying') : t('applyAndPromote')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
