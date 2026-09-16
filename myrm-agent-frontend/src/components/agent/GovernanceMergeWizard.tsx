'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives/select';
import { GitMerge, Loader2, TriangleAlert } from 'lucide-react';
import {
  mergeDryRun,
  mergeExecute,
  rollbackAgentProfile,
  type GovernanceOverview,
  type MergeDryRun,
} from '@/services/agent';
import { toast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils';

export function MergeWizard({
  pair,
  agentNames,
  onClose,
  onDone,
}: {
  pair: GovernanceOverview['overlaps'][number];
  agentNames: Record<string, string>;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useTranslations('Agent.governance');
  const [targetId, setTargetId] = useState(pair.agent_a.id);
  const [sourceId, setSourceId] = useState(pair.agent_b.id);
  const [preview, setPreview] = useState<MergeDryRun | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [confirmName, setConfirmName] = useState('');
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [justMerged, setJustMerged] = useState(false);
  const [mergedTargetId, setMergedTargetId] = useState<string | null>(null);

  const allAgents = Object.entries(agentNames);

  const resetTransient = () => {
    setPreview(null);
    setConfirmName('');
    setResult(null);
    setJustMerged(false);
    setMergedTargetId(null);
  };

  const handleTargetChange = (next: string) => {
    setTargetId(next);
    resetTransient();
    if (next === sourceId) {
      const fallback = allAgents.find(([id]) => id !== next)?.[0];
      if (fallback) {
        setSourceId(fallback);
      }
    }
  };

  const handleSourceChange = (next: string) => {
    setSourceId(next);
    resetTransient();
  };

  const handlePreview = async () => {
    setLoadingPreview(true);
    setPreview(null);
    try {
      setPreview(await mergeDryRun(sourceId, targetId));
    } catch {
      toast.error(t('previewError', { fallback: 'Failed to preview merge.' }));
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleExecute = async () => {
    setExecuting(true);
    try {
      const res = await mergeExecute(sourceId, targetId, confirmName);
      if (!res.ok) {
        setResult(res.reason || t('executeRejected', { fallback: 'Merge rejected. Check the confirmation name.' }));
        return;
      }
      const failed = (res.steps || []).filter((s) => !s.ok);
      if (failed.length > 0) {
        setResult(
          t('executePartial', {
            fallback: `Completed with ${failed.length} failed step(s). Use rollback to undo.`,
          }),
        );
        setJustMerged(true);
        setMergedTargetId(targetId);
        onDone();
      } else {
        setResult(null);
        setJustMerged(true);
        setMergedTargetId(targetId);
        toast.success(t('executeOk', { fallback: 'Agents merged. Source archived.' }));
      }
    } catch {
      toast.error(t('executeError', { fallback: 'Failed to execute merge.' }));
    } finally {
      setExecuting(false);
    }
  };

  const handleUndo = async () => {
    if (!mergedTargetId) {
      return;
    }
    try {
      await rollbackAgentProfile(mergedTargetId);
      toast.success(t('undoOk', { fallback: 'Target agent restored.' }));
      setJustMerged(false);
      setMergedTargetId(null);
      onDone();
      onClose();
    } catch {
      toast.error(t('undoError', { fallback: 'Failed to restore target agent.' }));
    }
  };

  const handleClose = () => {
    onDone();
    onClose();
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) { handleClose(); } }}>
      <DialogContent className="sm:max-w-[560px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('wizardTitle', { fallback: 'Merge assistants' })}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>{t('mergeSource', { fallback: 'Archive (source)' })}</Label>
              <Select value={sourceId} onValueChange={handleSourceChange} disabled={justMerged}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {allAgents
                    .filter(([id]) => id !== targetId)
                    .map(([id, name]) => (
                      <SelectItem key={id} value={id}>
                        {name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t('keepTarget', { fallback: 'Keep (target)' })}</Label>
              <Select value={targetId} onValueChange={handleTargetChange} disabled={justMerged}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {allAgents
                    .filter(([id]) => id !== sourceId)
                    .map(([id, name]) => (
                      <SelectItem key={id} value={id}>
                        {name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {t('sourceNote', {
              fallback: `“${agentNames[sourceId] || ''}” will be archived after its skills and bindings move over.`,
            })}
          </p>

          <Button variant="outline" onClick={handlePreview} disabled={loadingPreview}>
            {loadingPreview && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('preview', { fallback: 'Preview changes' })}
          </Button>

          {preview?.ok && preview.plan && (
            <div className={cn('rounded-lg border p-3 text-sm space-y-1.5', 'border-border/60')}>
              <p>
                {t('planSkills', { fallback: 'Skills to move' })}: {preview.plan.move_skills.join(', ') || '—'}
              </p>
              <p>
                {t('planSubagents', { fallback: 'Subagents to move' })}: {preview.plan.move_subagents.join(', ') || '—'}
              </p>
              <p className="text-muted-foreground">{preview.plan.keep_tools_note}</p>
              {preview.plan.conflicts.map((c) => (
                <p key={c} className="flex items-start gap-1.5 text-amber-600 dark:text-amber-400">
                  <TriangleAlert className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{c}</span>
                </p>
              ))}
              {preview.affected && (
                <>
                  <p className="text-muted-foreground">
                    {t('planAffected', {
                      fallback: `${preview.affected.cron_jobs} scheduled tasks move over. Board tasks need manual reassignment.`,
                    })}
                  </p>
                  {(preview.affected.cron_names?.length || preview.affected.channel_topics?.length) && (
                    <p className="text-muted-foreground break-words">
                      {t('planBindings', { fallback: 'Bindings on the move' })}:{' '}
                      {[...(preview.affected.cron_names || []), ...(preview.affected.channel_topics || [])].join(
                        ', ',
                      )}
                      {(preview.affected.cron_truncated || preview.affected.channel_truncated) && ' …'}
                    </p>
                  )}
                </>
              )}
            </div>
          )}
          {preview && !preview.ok && (
            <p className="text-sm text-destructive">{preview.reason}</p>
          )}

          {result && <p className="text-sm text-destructive">{result}</p>}

          <div className="space-y-2">
            <Label htmlFor="merge-confirm">
              {t('confirmLabel', { fallback: 'Type the kept assistant name to confirm' })}
            </Label>
            <Input
              id="merge-confirm"
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
              placeholder={agentNames[targetId] || ''}
              autoComplete="off"
            />
          </div>
        </div>

        <DialogFooter className="gap-2">
          {justMerged && (
            <Button variant="ghost" onClick={handleUndo} disabled={executing}>
              {t('undo', { fallback: 'Restore target' })}
            </Button>
          )}
          <Button variant="outline" onClick={handleClose} disabled={executing}>
            {t(justMerged ? 'done' : 'cancel', { fallback: justMerged ? 'Done' : 'Cancel' })}
          </Button>
          <Button
            onClick={handleExecute}
            disabled={executing || justMerged || !preview?.ok || !confirmName.trim()}
          >
            {executing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('execute', { fallback: 'Merge now' })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
