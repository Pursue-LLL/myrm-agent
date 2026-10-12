'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::runMemoryCommandAction, runMemoryDiagnosticRepair, rollbackConsolidation (POS: Frontend Personal Brain Command Center client)
 * @/services/memory/archive::dryRunRollbackMemoryImport, rollbackMemoryImport, exportMemoryArchive (POS: Frontend Memory Archive and import API client)
 * @/services/memory/pendingTargetChanged::isPendingTargetChanged (POS: 待审建议所针对的记忆已变化时给出本地化「已过期」提示)
 *
 * [OUTPUT]
 * useMemoryCommandCenterActions: 命令中心写操作处理器与导入回滚弹窗状态
 *
 * [POS]
 * 命令中心写操作：治理决策、冲突裁决、Doctor 修复、导入回滚（预演后确认）、整合回滚、归档导出与迁移向导跳转。
 * 每个动作通过 toast 反馈结果，改变服务端状态后刷新快照。
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { toast } from '@/hooks/shared/useToast';
import {
  dryRunRollbackMemoryImport,
  exportMemoryArchive,
  rollbackMemoryImport,
  type MemoryArchiveSection,
  type MemoryImportRollbackPreviewResponse,
  type MemoryImportRollbackResponse,
} from '@/services/memory/archive';
import {
  rollbackConsolidation,
  runMemoryCommandAction,
  runMemoryDiagnosticRepair,
  type MemoryCommandDiagnosticRun,
  type MemoryCommandGovernanceItem,
} from '@/services/memory/commandCenter';
import { canDeepLinkMigrationSource } from '@/services/migrationDiscovery';
import { isPendingTargetChanged } from '@/services/memory/pendingTargetChanged';
import type { DoctorExecutableAction } from '../command-center/MemoryCommandCenterDoctorPanel';

const totalArchiveItems = (sections: MemoryArchiveSection[]): number =>
  sections.reduce((total, section) => total + section.item_count, 0);

interface UseMemoryCommandCenterActionsOptions {
  loadSnapshot: () => Promise<void>;
  setActionId: (actionId: string | null) => void;
  showVerifySection: () => void;
  setDiagnosticRun: (run: MemoryCommandDiagnosticRun) => void;
}

export const useMemoryCommandCenterActions = ({
  loadSnapshot,
  setActionId,
  showVerifySection,
  setDiagnosticRun,
}: UseMemoryCommandCenterActionsOptions) => {
  const t = useTranslations('memory');
  const router = useRouter();
  const [rollbackPreview, setRollbackPreview] = useState<MemoryImportRollbackPreviewResponse | null>(null);
  const [rollbackResult, setRollbackResult] = useState<MemoryImportRollbackResponse | null>(null);
  const [rollbackDialogOpen, setRollbackDialogOpen] = useState(false);

  const runAction = useCallback(
    async (item: MemoryCommandGovernanceItem, action: 'approve' | 'reject') => {
      setActionId(`${item.target_kind}:${item.id}:${action}`);
      try {
        await runMemoryCommandAction({
          target_kind: item.target_kind,
          target_id: item.id,
          action,
          memory_type: item.title,
        });
        toast({ title: t('commandCenter.actionSuccess') });
        await loadSnapshot();
      } catch (err) {
        const stale = isPendingTargetChanged(err);
        toast({
          title: stale ? t('targetChangedTitle') : t('commandCenter.actionFailed'),
          description: stale ? t('targetChangedDesc') : err instanceof Error ? err.message : t('unknownError'),
          variant: stale ? 'default' : 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [loadSnapshot, setActionId, t],
  );

  const resolveConflict = useCallback(
    async (conflictId: string, action: 'keep_new' | 'keep_old' | 'coexist') => {
      setActionId(`conflict:${conflictId}:${action}`);
      try {
        await runMemoryCommandAction({
          target_kind: 'conflict_pair',
          target_id: conflictId,
          action,
        });
        toast({ title: t('commandCenter.actionSuccess') });
        await loadSnapshot();
      } catch (err) {
        toast({
          title: t('commandCenter.actionFailed'),
          description: err instanceof Error ? err.message : t('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [loadSnapshot, setActionId, t],
  );

  const runDoctorAction = useCallback(
    async (action: DoctorExecutableAction) => {
      showVerifySection();
      setActionId(`diagnostics:${action}`);
      try {
        const result = await runMemoryDiagnosticRepair({ plan_id: action, mode: 'execute' });
        if (result.run) {
          setDiagnosticRun(result.run);
        }
        toast({
          title:
            result.result.status === 'completed'
              ? t('commandCenter.diagnosticCompleted')
              : t('commandCenter.diagnosticCompletedWithFindings'),
          description: result.result.message,
        });
        await loadSnapshot();
      } catch (err) {
        toast({
          title: t('commandCenter.actionFailed'),
          description: err instanceof Error ? err.message : t('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [loadSnapshot, setActionId, setDiagnosticRun, showVerifySection, t],
  );

  const previewRollbackImport = useCallback(
    async (importBatchId: string) => {
      setActionId(`migration:rollback-preview:${importBatchId}`);
      try {
        setRollbackPreview(await dryRunRollbackMemoryImport(importBatchId));
        setRollbackResult(null);
        setRollbackDialogOpen(true);
      } catch (err) {
        toast({
          title: t('commandCenter.actionFailed'),
          description: err instanceof Error ? err.message : t('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [setActionId, t],
  );

  const confirmRollbackImport = useCallback(async () => {
    if (!rollbackPreview) {
      return;
    }
    const importBatchId = rollbackPreview.import_batch_id;
    setActionId(`migration:rollback:${importBatchId}`);
    try {
      const result = await rollbackMemoryImport(importBatchId);
      setRollbackResult(result);
      toast({
        title: t('commandCenter.rollbackSuccess'),
        description: t('commandCenter.rollbackSuccessDesc', {
          count: result.total_rolled_back,
          missing: result.missing_items,
          failed: result.failed_items,
        }),
      });
      await loadSnapshot();
    } catch (err) {
      toast({
        title: t('commandCenter.actionFailed'),
        description: err instanceof Error ? err.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [loadSnapshot, rollbackPreview, setActionId, t]);

  const openMigrationWizard = useCallback(
    (source: string) => {
      const normalizedSource = source.trim().toLowerCase();
      const sourceQuery = canDeepLinkMigrationSource(normalizedSource)
        ? `&source=${encodeURIComponent(normalizedSource)}`
        : '';
      router.push(`/settings/memory?sub=migration${sourceQuery}`);
    },
    [router],
  );

  const handleConsolidationRollback = useCallback(async () => {
    setActionId('consolidation:rollback');
    try {
      const result = await rollbackConsolidation();
      toast({
        title: t('commandCenter.consolidationRollbackSuccess'),
        description: t('commandCenter.consolidationRollbackSuccessDesc', {
          count: result.rolled_back,
          conflicts: result.skipped_conflict,
        }),
      });
      await loadSnapshot();
    } catch (err) {
      toast({
        title: t('commandCenter.actionFailed'),
        description: err instanceof Error ? err.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [loadSnapshot, setActionId, t]);

  const exportArchive = useCallback(async () => {
    setActionId('archive:export');
    try {
      const { archive } = await exportMemoryArchive();
      const payload = JSON.stringify(archive, null, 2);
      const blob = new Blob([payload], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `myrm-memory-archive-${archive.manifest.created_at.replaceAll(':', '-')}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast({
        title: t('commandCenter.archiveExportSuccess'),
        description: t('commandCenter.archiveExportSuccessDesc', {
          count: totalArchiveItems(archive.manifest.sections),
          sections: archive.manifest.sections.length,
        }),
      });
    } catch (err) {
      toast({
        title: t('commandCenter.actionFailed'),
        description: err instanceof Error ? err.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [setActionId, t]);

  return {
    runAction,
    resolveConflict,
    runDoctorAction,
    previewRollbackImport,
    confirmRollbackImport,
    openMigrationWizard,
    handleConsolidationRollback,
    exportArchive,
    rollbackPreview,
    rollbackResult,
    rollbackDialogOpen,
    setRollbackDialogOpen,
  };
};
