/**
 * [INPUT] @/services/memory::{exportMemories, exportMemoriesMarkdown} + @/services/memory/archive::{dryRunImportMemories, confirmImportMemories} (POS: 导出 / 导入接口), @/lib/utils/fileUtils::triggerDownload (POS: 保存文件), ./memoryImportFile (POS: 导入文件解析), ./memoryNotices (POS: 结果提示)
 * [OUTPUT] useMemoryImportExport / MemoryImportExport: 记忆的 JSON / Markdown 导出，以及“选文件 → dry-run 预检 → 审阅确认”的导入流程状态与动作
 * [POS] 记忆面板的导入导出状态层：导出 JSON 经 triggerDownload（桌面端走系统保存对话框，取消保存不提示成功）；导入先预检再弹审阅框，确认成功后刷新记忆列表；每次选文件后清空 input，同一文件可再次选择。
 */

import { useCallback, useRef, useState, type ChangeEvent } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { triggerDownload } from '@/lib/utils/fileUtils';
import { exportMemories, exportMemoriesMarkdown } from '@/services/memory';
import { confirmImportMemories, dryRunImportMemories, type MemoryImportDryRunResult } from '@/services/memory/archive';
import { MAX_IMPORT_SIZE_MB, isImportFileTooLarge, readImportPayload } from './memoryImportFile';
import { notifyImportOutcome, toastFailure } from './memoryNotices';

interface PendingImport {
  dryRun: MemoryImportDryRunResult;
  dryRunId: string;
  expiresAt: string | null;
}

export function useMemoryImportExport(refreshMemories: () => Promise<void>) {
  const t = useTranslations('memory');
  const tWizard = useTranslations('memory.migrationWizard');
  const importInputRef = useRef<HTMLInputElement>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isExportingMd, setIsExportingMd] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  /** The dry-run awaiting the user's review; the review dialog is open exactly while this is set. */
  const [pendingImport, setPendingImport] = useState<PendingImport | null>(null);

  const clearImportInput = useCallback(() => {
    if (importInputRef.current) {
      importInputRef.current.value = '';
    }
  }, []);

  const handleExport = useCallback(async () => {
    setIsExporting(true);
    try {
      const result = await exportMemories();
      if (result.total_count === 0) {
        toast({ title: t('noMemoriesToExport'), variant: 'destructive' });
        return;
      }
      const json = JSON.stringify({ version: result.version, data: result.data }, null, 2);
      const filename = `memories-${new Date().toISOString().slice(0, 10)}.json`;
      if (await triggerDownload(new Blob([json], { type: 'application/json' }), filename)) {
        toast({ title: t('exportSuccess'), description: t('exportSuccessDesc', { count: result.total_count }) });
      }
    } catch (error) {
      toastFailure(t, t('exportFailed'), error);
    } finally {
      setIsExporting(false);
    }
  }, [t]);

  const handleExportMarkdown = useCallback(async () => {
    setIsExportingMd(true);
    try {
      await exportMemoriesMarkdown();
      toast({ title: t('exportSuccess') });
    } catch (error) {
      toastFailure(t, t('exportFailed'), error);
    } finally {
      setIsExportingMd(false);
    }
  }, [t]);

  const handleImportFile = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) {
        return;
      }
      if (isImportFileTooLarge(file)) {
        toast({
          title: t('importFailed'),
          description: t('importFileTooLarge', { maxMb: MAX_IMPORT_SIZE_MB }),
          variant: 'destructive',
        });
        clearImportInput();
        return;
      }

      setIsImporting(true);
      try {
        const { payload, source } = await readImportPayload(file, t('importJsonlNoValidLines'));
        const dryRun = await dryRunImportMemories(payload, source);
        setPendingImport({ dryRun: dryRun.result, dryRunId: dryRun.dry_run_id, expiresAt: dryRun.expires_at });
      } catch (error) {
        toastFailure(t, t('importFailed'), error);
      } finally {
        setIsImporting(false);
        clearImportInput();
      }
    },
    [t, clearImportInput],
  );

  const dryRunId = pendingImport?.dryRunId;
  const handleConfirmImport = useCallback(async () => {
    if (!dryRunId) {
      return;
    }
    setIsImporting(true);
    try {
      notifyImportOutcome(await confirmImportMemories(dryRunId, true), t, tWizard);
      setPendingImport(null);
      await refreshMemories();
    } catch (error) {
      toastFailure(t, t('importFailed'), error);
    } finally {
      setIsImporting(false);
    }
  }, [dryRunId, refreshMemories, t, tWizard]);

  const handleImportReviewOpenChange = useCallback((open: boolean) => {
    if (!open) {
      setPendingImport(null);
    }
  }, []);

  return {
    importInputRef,
    isImporting,
    isExporting,
    isExportingMd,
    pendingImport,
    handleExport,
    handleExportMarkdown,
    handleImportFile,
    handleConfirmImport,
    handleImportReviewOpenChange,
  };
}

export type MemoryImportExport = ReturnType<typeof useMemoryImportExport>;
