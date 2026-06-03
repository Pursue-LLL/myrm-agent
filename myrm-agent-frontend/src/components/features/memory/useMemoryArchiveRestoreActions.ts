'use client';

/**
 * [INPUT]
 * @/services/memoryArchive::*ArchiveRestore* (POS: Frontend Memory Archive and import API client)
 * command-center refresh callback.
 *
 * [OUTPUT]
 * State and handlers for Memory Archive restore file selection, confirm, and rollback.
 *
 * [POS]
 * 归档恢复 UI 编排 Hook。容器只负责放置按钮和弹窗，恢复流程细节集中在这里。
 */

import { useCallback, useRef, useState, type ChangeEvent } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/useToast';
import {
  confirmArchiveRestore,
  dryRunArchiveRestore,
  dryRunArchiveRestoreRollback,
  getDefaultArchiveRestoreSections,
  MemoryArchiveFileError,
  parseMemoryArchiveFile,
  rollbackArchiveRestore,
  type MemoryArchivePayload,
  type MemoryArchiveRestoreDryRunResult,
  type MemoryArchiveRestoreResult,
  type MemoryArchiveRestoreRollbackPreview,
  type MemoryArchiveRestoreRollbackResult,
  type MemoryArchiveSectionName,
} from '@/services/memoryArchive';

export const useMemoryArchiveRestoreActions = ({
  setActionId,
  loadSnapshot,
}: {
  setActionId: (actionId: string | null) => void;
  loadSnapshot: () => Promise<void>;
}) => {
  const t = useTranslations('memory');
  const [open, setOpen] = useState(false);
  const [payload, setPayload] = useState<MemoryArchivePayload | null>(null);
  const [preview, setPreview] = useState<MemoryArchiveRestoreDryRunResult | null>(null);
  const [result, setResult] = useState<MemoryArchiveRestoreResult | null>(null);
  const [rollbackPreview, setRollbackPreview] = useState<MemoryArchiveRestoreRollbackPreview | null>(null);
  const [rollbackResult, setRollbackResult] = useState<MemoryArchiveRestoreRollbackResult | null>(null);
  const [selectedSections, setSelectedSections] = useState<MemoryArchiveSectionName[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const selectFile = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const handleFile = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) return;
      setActionId('archive:restore-dry-run');
      try {
        const raw = await parseMemoryArchiveFile(file);
        const sections = getDefaultArchiveRestoreSections(raw);
        const response = await dryRunArchiveRestore(raw, sections);
        setPayload(raw);
        setSelectedSections(sections);
        setPreview(response.result);
        setResult(null);
        setRollbackPreview(null);
        setRollbackResult(null);
        setOpen(true);
      } catch (err) {
        toast({
          title: t('commandCenter.actionFailed'),
          description: archiveRestoreErrorMessage(t, err),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [setActionId, t],
  );

  const toggleSection = useCallback(
    async (section: MemoryArchiveSectionName) => {
      if (!payload) return;
      const nextSections = selectedSections.includes(section)
        ? selectedSections.filter((selected) => selected !== section)
        : [...selectedSections, section];
      if (nextSections.length === 0) {
        toast({
          title: t('commandCenter.actionFailed'),
          description: t('archiveRestore.selectAtLeastOneSection'),
          variant: 'destructive',
        });
        return;
      }
      setActionId('archive:restore-dry-run');
      try {
        const response = await dryRunArchiveRestore(payload, nextSections);
        setSelectedSections(nextSections);
        setPreview(response.result);
        setResult(null);
        setRollbackPreview(null);
        setRollbackResult(null);
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
    [payload, selectedSections, setActionId, t],
  );

  const confirm = useCallback(async () => {
    if (!payload || !preview) return;
    setActionId('archive:restore-confirm');
    try {
      const response = await confirmArchiveRestore(
        payload,
        preview.payload_hash,
        preview.plan.plan_hash,
        selectedSections,
      );
      setResult(response.result);
      toast({
        title: t('commandCenter.archiveRestoreSuccess'),
        description: t('commandCenter.archiveRestoreSuccessDesc', {
          count: response.result.total_restored,
          conflicts: response.result.conflict_items,
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
  }, [loadSnapshot, payload, preview, selectedSections, setActionId, t]);

  const rollback = useCallback(async () => {
    if (!result) return;
    setActionId(`archive:restore-rollback:${result.restore_batch_id}`);
    try {
      const previewResponse = await dryRunArchiveRestoreRollback(result.restore_batch_id);
      setRollbackPreview(previewResponse.result);
      if (previewResponse.result.reversible_items === 0) {
        toast({
          title: t('commandCenter.actionFailed'),
          description: t('commandCenter.archiveRestoreRollbackEmpty'),
          variant: 'destructive',
        });
        return;
      }
      const rollbackResponse = await rollbackArchiveRestore(result.restore_batch_id);
      setRollbackResult(rollbackResponse.result);
      toast({
        title: t('commandCenter.archiveRestoreRollbackSuccess'),
        description: t('commandCenter.archiveRestoreRollbackSuccessDesc', {
          count: rollbackResponse.result.total_rolled_back,
          missing: rollbackResponse.result.missing_items,
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
  }, [loadSnapshot, result, setActionId, t]);

  return {
    inputRef,
    open,
    setOpen,
    preview,
    result,
    rollbackPreview,
    rollbackResult,
    selectedSections,
    selectFile,
    handleFile,
    toggleSection,
    confirm,
    rollback,
  };
};

const archiveRestoreErrorMessage = (t: ReturnType<typeof useTranslations<'memory'>>, error: unknown): string => {
  if (error instanceof MemoryArchiveFileError) {
    return t(`archiveRestore.fileErrors.${error.code}`, error.params);
  }
  return error instanceof Error ? error.message : t('unknownError');
};
