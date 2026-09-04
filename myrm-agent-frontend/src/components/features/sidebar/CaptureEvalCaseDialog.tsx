'use client';

/**
 * [INPUT] @/services/eval, @/components/primitives/dialog, @/hooks/shared/useToast
 * [OUTPUT] CaptureEvalCaseDialog: 会话一键沉淀为评测用例对话框
 * [POS] 供 ChatHistoryList 挂载，由 ChatHistoryRow 右键菜单触发，支持拉取已有数据集或输入新数据集，将当前会话提取并固化为私有回归用例。
 */

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { FlaskConical, Database, Plus, Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { evalService, type EvalDatasetItem } from '@/services/eval';
import { useToast } from '@/hooks/shared/useToast';

interface CaptureEvalCaseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId: string | null;
  onSuccess?: () => void;
}

export function CaptureEvalCaseDialog({
  open,
  onOpenChange,
  chatId,
  onSuccess,
}: CaptureEvalCaseDialogProps) {
  const t = useTranslations();
  const { toast } = useToast();
  const [datasets, setDatasets] = useState<EvalDatasetItem[]>([]);
  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [selectedDatasetId, setSelectedDatasetId] = useState('default');
  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    setLoadingDatasets(true);
    setIsCreatingNew(false);
    setNewDatasetName('');
    evalService
      .getDatasets()
      .then((res) => {
        if (res.datasets && res.datasets.length > 0) {
          setDatasets(res.datasets);
          setSelectedDatasetId(res.datasets[0].id);
        } else {
          setDatasets([{ id: 'default', name: 'default' }]);
          setSelectedDatasetId('default');
        }
      })
      .catch((err: unknown) => {
        console.error('Failed to load datasets:', err);
        setDatasets([{ id: 'default', name: 'default' }]);
        setSelectedDatasetId('default');
      })
      .finally(() => setLoadingDatasets(false));
  }, [open]);

  const handleConfirm = async () => {
    if (!chatId) return;

    const targetDatasetId = isCreatingNew
      ? newDatasetName.trim().replace(/[^a-zA-Z0-9_-]/g, '_').replace(/^_+|_+$/g, '')
      : selectedDatasetId.trim();

    if (!targetDatasetId) {
      toast({
        title: t('chat.captureEvalCase.error'),
        description: t('chat.captureEvalCase.emptyDatasetError') || 'Dataset name cannot be empty',
        variant: 'destructive',
      });
      return;
    }

    setSubmitting(true);
    try {
      await evalService.captureCaseFromChat(chatId, targetDatasetId);
      toast({
        title: t('chat.captureEvalCase.success') || 'Captured as Eval Case',
        description: t('chat.captureEvalCase.successDesc') || 'Chat session has been appended to the evaluation dataset.',
      });
      onOpenChange(false);
      onSuccess?.();
    } catch (error: unknown) {
      console.error('Failed to capture eval case:', error);
      toast({
        title: t('chat.captureEvalCase.error') || 'Capture Failed',
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <FlaskConical className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold">
                {t('chat.captureEvalCase.title') || 'Capture as Evaluation Case'}
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                {t('chat.captureEvalCase.description') ||
                  'Preserve this chat session as a regression test case in your private evaluation lab.'}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="py-3 space-y-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5 text-muted-foreground" />
              <span>{t('chat.captureEvalCase.selectDataset') || 'Target Dataset'}</span>
            </label>

            {loadingDatasets ? (
              <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                <span>{t('common.loading') || 'Loading...'}</span>
              </div>
            ) : (
              <div className="space-y-2">
                {!isCreatingNew ? (
                  <div className="flex gap-2">
                    <select
                      value={selectedDatasetId}
                      onChange={(e) => setSelectedDatasetId(e.target.value)}
                      className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-xs ring-offset-background focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      {datasets.map((ds) => (
                        <option key={ds.id} value={ds.id}>
                          {ds.name || ds.id} {ds.count !== undefined ? `(${ds.count})` : ''}
                        </option>
                      ))}
                    </select>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setIsCreatingNew(true)}
                      className="h-8 text-xs gap-1"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>{t('chat.captureEvalCase.newDataset') || 'New'}</span>
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={newDatasetName}
                      onChange={(e) => setNewDatasetName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          handleConfirm();
                        }
                      }}
                      placeholder={t('chat.captureEvalCase.newDatasetPlaceholder') || 'Enter dataset name (e.g., regressions)'}
                      className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-xs ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      autoFocus
                    />
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => setIsCreatingNew(false)}
                        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {t('chat.captureEvalCase.chooseExisting') || 'Choose existing dataset'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="flex gap-2 sm:justify-end">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            {t('common.cancel') || 'Cancel'}
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleConfirm}
            disabled={submitting || loadingDatasets}
            className="gap-1.5"
          >
            {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            <span>{t('chat.captureEvalCase.confirm') || 'Capture'}</span>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
