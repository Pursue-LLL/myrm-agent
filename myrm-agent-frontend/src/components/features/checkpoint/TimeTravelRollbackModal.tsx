'use client';

/**
 * Dialog to review the file changes of an unattended goal run and undo them in one step.
 *
 * [INPUT]
 * - @/services/airbag::rollbackAirbag (POS: 触发一键撤销接口)
 * - @/services/airbag::dismissAirbag (POS: 确认保留改动、关闭撤销入口接口)
 * - ./externalEffectLabels::formatExternalEffects (POS: 外部影响类别文案映射)
 * - @/hooks/shared/useToast::toast (POS: 全局轻提示交互钩子)
 *
 * [OUTPUT]
 * - TimeTravelRollbackModal: 审查并撤销改动对话框；撤销或保留成功后调用 `onResolved`
 *
 * [POS]
 * 前端检查点特性层：无人值守长任务的改动审查与一键撤销交互弹窗。
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldCheck, AlertTriangle, RotateCcw, FileEdit, FilePlus, FileMinus } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { AirbagStatusResponse, rollbackAirbag, dismissAirbag } from '@/services/airbag';
import { toast } from '@/hooks/shared/useToast';
import { formatExternalEffects } from './externalEffectLabels';

interface TimeTravelRollbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  status: AirbagStatusResponse;
  workspacePath?: string;
  onResolved?: () => void;
}

const FILE_KINDS = [
  { key: 'modifiedFiles', label: 'modified', Icon: FileEdit, tone: 'text-blue-500', dot: 'bg-blue-500' },
  { key: 'addedFiles', label: 'added', Icon: FilePlus, tone: 'text-emerald-500', dot: 'bg-emerald-500' },
  { key: 'deletedFiles', label: 'deleted', Icon: FileMinus, tone: 'text-rose-500', dot: 'bg-rose-500' },
] as const;

export const TimeTravelRollbackModal: React.FC<TimeTravelRollbackModalProps> = ({
  isOpen,
  onClose,
  status,
  workspacePath,
  onResolved,
}) => {
  const t = useTranslations('taskAirbag');
  const tFileSnapshot = useTranslations('fileSnapshot');
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [isDismissing, setIsDismissing] = useState(false);

  const handleRollback = async () => {
    setIsRollingBack(true);
    try {
      const res = await rollbackAirbag(status.taskId, workspacePath);
      if (res.success && res.status === 'rolled_back') {
        toast({
          title: t('undoneTitle'),
          description: res.rescueSnapshotId ? t('undoneWithBackup') : t('undone'),
          variant: 'default',
        });
        window.dispatchEvent(new CustomEvent('app_resync_required'));
        onResolved?.();
        onClose();
      } else {
        toast({ title: t('undoFailedTitle'), description: t('undoFailed'), variant: 'destructive' });
      }
    } catch (err) {
      toast({
        title: t('undoErrorTitle'),
        description: err instanceof Error ? err.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsRollingBack(false);
    }
  };

  const handleDismiss = async () => {
    setIsDismissing(true);
    try {
      const res = await dismissAirbag(status.taskId, workspacePath);
      if (res.success) {
        toast({ title: t('keptTitle'), description: t('kept'), variant: 'default' });
        onResolved?.();
        onClose();
      }
    } catch {
      toast({ title: t('keepFailedTitle'), variant: 'destructive' });
    } finally {
      setIsDismissing(false);
    }
  };

  const hasDetectedEffects = status.externalEffects.length > 0;
  const busy = isRollingBack || isDismissing;

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !busy) {
          onClose();
        }
      }}
    >
      <DialogContent className="flex max-h-[90vh] w-[calc(100%-1.5rem)] max-w-xl flex-col gap-0 overflow-hidden p-0 sm:w-full">
        <DialogHeader className="flex-row items-center gap-2.5 space-y-0 border-b border-border bg-muted/30 px-4 py-4 pr-12 text-left sm:px-5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div className="min-w-0 space-y-0.5">
            <DialogTitle className="text-base leading-snug">{t('modalTitle')}</DialogTitle>
            <DialogDescription className="text-xs">{t('modalSubtitle')}</DialogDescription>
          </div>
        </DialogHeader>

        <div className="p-4 sm:p-5 overflow-y-auto space-y-4 text-sm">
          <div
            className={`rounded-lg border p-3.5 space-y-1.5 text-xs ${
              hasDetectedEffects
                ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400'
                : 'border-border bg-muted/40 text-muted-foreground'
            }`}
          >
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-px" />
              <span>{t('externalNote')}</span>
            </div>
            {hasDetectedEffects && (
              <p className="pl-6 font-medium">
                {t('externalDetected', { effects: formatExternalEffects(status.externalEffects, tFileSnapshot) })}
              </p>
            )}
          </div>

          <div className="grid grid-cols-3 gap-2 sm:gap-3">
            {FILE_KINDS.map(({ key, label, Icon, tone }) => (
              <div key={key} className="p-3 rounded-lg bg-muted/40 border border-border/50 text-center">
                <div className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground mb-1">
                  <Icon className={`w-3.5 h-3.5 shrink-0 ${tone}`} />
                  <span>{t(label)}</span>
                </div>
                <div className="text-lg font-semibold text-foreground">{status[key].length}</div>
              </div>
            ))}
          </div>

          <div className="space-y-1.5">
            <div className="text-xs font-medium text-muted-foreground">
              {t('fileListTitle', { count: status.totalFilesChanged })}
            </div>
            <div className="max-h-48 overflow-y-auto rounded-lg border border-border bg-muted/20 p-2 space-y-1 font-mono text-xs">
              {FILE_KINDS.flatMap(({ key, label, dot }) =>
                status[key].map((file) => (
                  <div key={`${key}-${file}`} className="flex items-center gap-2 text-foreground/90">
                    <span aria-hidden className={`size-2 rounded-full shrink-0 ${dot}`} />
                    <span className="sr-only">{t(label)}</span>
                    <span className="truncate">{file}</span>
                  </div>
                )),
              )}
              {status.totalFilesChanged === 0 && (
                <div className="text-center py-4 text-muted-foreground font-sans">{t('noChanges')}</div>
              )}
            </div>
          </div>
        </div>

        <DialogFooter className="flex-col-reverse gap-2 border-t border-border bg-muted/20 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:space-x-0 sm:px-5">
          <button
            type="button"
            onClick={handleDismiss}
            disabled={busy}
            className="px-3.5 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50"
          >
            {isDismissing ? t('keeping') : t('keepChanges')}
          </button>

          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="px-3.5 py-1.5 rounded-lg border border-transparent text-xs font-medium text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              {t('later')}
            </button>
            <button
              type="button"
              onClick={handleRollback}
              disabled={busy || !status.canRollback || status.totalFilesChanged === 0}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium shadow transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${isRollingBack ? 'animate-spin' : ''}`} />
              <span>{isRollingBack ? t('undoing') : t('undoAll')}</span>
            </button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
