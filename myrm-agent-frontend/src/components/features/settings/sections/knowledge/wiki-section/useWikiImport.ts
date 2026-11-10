/**
 * [INPUT] @/services/wikiService::wikiService (POS: Wiki 导入接口: 文件夹、ZIP、Obsidian、链接、视频), @/lib/migrationChatHandoff (POS: 迁移向导交接的 Obsidian vault 路径), @/lib/utils/clipboardUtils::isTauri (POS: 桌面端判断), ./useWikiOverviewData (POS: 统计重载与原文树同步)
 * [OUTPUT] useWikiImport: 批量导入与 Obsidian 导入的状态、选择器引用与动作, 导入冲突 / 安全提示 / 链接 / 视频对话框的开关与回调
 * [POS] Wiki 面板的导入层: 导入结果按界面语言汇总（文件夹与 ZIP 报告导入与跳过的文件数, Obsidian 报告笔记、标签与图片数）, 汇总形式取决于结果本身的形状; 总会重读统计, 有文件入队时才提示重复扫描并切到重复审核页; 命中冲突时保留重试信息, 用户选择“覆盖”后以 supersede 重试; 迁移向导交接的 vault 路径在首次进入时自动导入一次。
 */

import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { consumeMigrationObsidianVaultImport } from '@/lib/migrationChatHandoff';
import { isTauri } from '@/lib/utils/clipboardUtils';
import {
  wikiService,
  type ImportResultResponse,
  type ImportUrlsResultResponse,
  type ImportVideoResponse,
  type ObsidianImportResultResponse,
  type WikiImportConflictOptions,
} from '@/services/wikiService';
import type { WikiOverviewData } from './useWikiOverviewData';

interface PendingImportRetry {
  kind: 'folder' | 'zip' | 'obsidian-folder' | 'obsidian-zip';
  folderPath?: string;
  zipFile?: File;
}

type ImportOutcome = ImportResultResponse | ObsidianImportResultResponse;

/** An Obsidian import answers with note counts, a folder or ZIP import with file counts. */
const isObsidianResult = (result: ImportOutcome): result is ObsidianImportResultResponse => 'files_processed' in result;

interface UseWikiImportParams {
  agentScopeId: string | null;
  overview: Pick<WikiOverviewData, 'loadStats' | 'bumpTreeSync'>;
  handleWikiTabChange: (tab: string) => void;
  goToKnowledgeGraph: () => void;
}

export function useWikiImport({
  agentScopeId,
  overview,
  handleWikiTabChange,
  goToKnowledgeGraph,
}: UseWikiImportParams) {
  const t = useTranslations('settings.wiki');
  const { loadStats, bumpTreeSync } = overview;
  const [isImporting, setIsImporting] = useState(false);
  const [isImportingObsidian, setIsImportingObsidian] = useState(false);
  const [urlImportDialogOpen, setUrlImportDialogOpen] = useState(false);
  const [videoImportDialogOpen, setVideoImportDialogOpen] = useState(false);
  const zipInputRef = useRef<HTMLInputElement>(null);
  const obsidianZipRef = useRef<HTMLInputElement>(null);
  const webFolderInputRef = useRef<HTMLInputElement>(null);
  const [importConflictOpen, setImportConflictOpen] = useState(false);
  const [importConflictPaths, setImportConflictPaths] = useState<string[]>([]);
  const [importSecurityOpen, setImportSecurityOpen] = useState(false);
  const [importSecurityBlockedPaths, setImportSecurityBlockedPaths] = useState<string[]>([]);
  const [importSecurityRedactedPaths, setImportSecurityRedactedPaths] = useState<string[]>([]);
  const [pendingImportRetry, setPendingImportRetry] = useState<PendingImportRetry | null>(null);

  const isTauriEnv = isTauri();

  const showObsidianResult = (result: ObsidianImportResultResponse) => {
    toast.success(
      t('import.obsidianResult', {
        processed: result.files_processed,
        tags: result.tags_extracted,
        images: result.images_copied,
        skipped: result.files_skipped + (result.files_skipped_conflict ?? 0),
      }),
    );
    toast.message(t('obsidianVault.postWorkflowHint'), {
      action: { label: t('obsidianVault.postWorkflowAction'), onClick: goToKnowledgeGraph },
    });
  };

  const showFolderResult = (result: ImportResultResponse) => {
    if (result.files_scanned === 0) {
      toast.message(t('import.noFilesFound'));
      return;
    }
    const skipped = result.files_scanned - result.files_enqueued;
    toast.success(
      skipped > 0
        ? t('import.folderResultWithSkips', { imported: result.files_enqueued, skipped })
        : t('import.folderResult', { imported: result.files_enqueued }),
    );
  };

  const finishImportResult = async (result: ImportOutcome, retry: PendingImportRetry | null) => {
    if (result.success) {
      if (isObsidianResult(result)) {
        showObsidianResult(result);
      } else {
        showFolderResult(result);
      }
      // The server starts its duplicate scan only when it queued files.
      if (result.files_enqueued > 0) {
        toast.message(t('import.dedupScanStarted'));
        handleWikiTabChange('duplicateReview');
      }
      await loadStats();
      const blocked = result.security_blocked_paths ?? [];
      const redacted = result.security_redacted_paths ?? [];
      if (blocked.length > 0 || redacted.length > 0) {
        setImportSecurityBlockedPaths(blocked);
        setImportSecurityRedactedPaths(redacted);
        setImportSecurityOpen(true);
      }
      const conflicts = result.conflict_paths ?? [];
      if (conflicts.length > 0 && retry) {
        setImportConflictPaths(conflicts);
        setPendingImportRetry(retry);
        setImportConflictOpen(true);
      }
    } else {
      toast.error(t('errors.importFailed'));
    }
  };

  const migrationVaultHandoffRef = useRef(false);
  const finishMigrationVaultImport = useEffectEvent(finishImportResult);
  useEffect(() => {
    if (migrationVaultHandoffRef.current || typeof window === 'undefined') {
      return;
    }
    if (!window.location.hash.includes('wiki-obsidian-import')) {
      return;
    }
    const handoff = consumeMigrationObsidianVaultImport(agentScopeId ?? undefined);
    if (!handoff?.vaultPath) {
      return;
    }
    migrationVaultHandoffRef.current = true;
    document.getElementById('wiki-obsidian-import')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    toast.message(t('import.migrationVaultHandoff', { path: handoff.vaultPath }));
    setIsImportingObsidian(true);
    void wikiService
      .importObsidianFolder(handoff.vaultPath, true, agentScopeId)
      .then(async (result) => {
        await finishMigrationVaultImport(result, { kind: 'obsidian-folder', folderPath: handoff.vaultPath });
      })
      .catch(() => {
        toast.error(t('import.migrationVaultHandoffFailed'));
      })
      .finally(() => {
        setIsImportingObsidian(false);
      });
  }, [agentScopeId, t]);

  const retryImportWithSupersede = async (reason: string) => {
    if (!pendingImportRetry) {
      setImportConflictOpen(false);
      return;
    }

    const conflictOptions: WikiImportConflictOptions = {
      onConflict: 'supersede',
      supersedeReason: reason,
    };

    setImportConflictOpen(false);
    setImportConflictPaths([]);
    const retry = pendingImportRetry;
    setPendingImportRetry(null);

    try {
      if (retry.kind === 'folder' && retry.folderPath) {
        setIsImporting(true);
        const result = await wikiService.importFolder(
          retry.folderPath,
          ['.md', '.txt', '.org'],
          true,
          agentScopeId,
          conflictOptions,
        );
        await finishImportResult(result, null);
      } else if (retry.kind === 'zip' && retry.zipFile) {
        setIsImporting(true);
        const result = await wikiService.importZip(retry.zipFile, '.md,.txt,.org', true, agentScopeId, conflictOptions);
        await finishImportResult(result, null);
      } else if (retry.kind === 'obsidian-folder' && retry.folderPath) {
        setIsImportingObsidian(true);
        const result = await wikiService.importObsidianFolder(retry.folderPath, true, agentScopeId, conflictOptions);
        await finishImportResult(result, null);
      } else if (retry.kind === 'obsidian-zip' && retry.zipFile) {
        setIsImportingObsidian(true);
        const result = await wikiService.importObsidianZip(retry.zipFile, true, agentScopeId, conflictOptions);
        await finishImportResult(result, null);
      }
    } catch (error) {
      console.error('Import supersede retry failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImporting(false);
      setIsImportingObsidian(false);
    }
  };

  const handleImportFolder = async () => {
    if (isTauriEnv) {
      try {
        const { open } = await import('@tauri-apps/plugin-dialog');
        const selected = await open({ directory: true, multiple: false, title: t('import.selectFolder') });
        if (!selected) {
          return;
        }

        setIsImporting(true);
        const folderPath = selected as string;
        const result = await wikiService.importFolder(folderPath, ['.md', '.txt', '.org'], true, agentScopeId);
        await finishImportResult(result, { kind: 'folder', folderPath });
      } catch (error) {
        console.error('Folder import failed:', error);
        toast.error(t('errors.importFailed'));
      } finally {
        setIsImporting(false);
      }
    } else {
      webFolderInputRef.current?.click();
    }
  };

  const handleWebFolderSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) {
      return;
    }

    setIsImporting(true);
    try {
      const { default: JSZip } = await import('jszip');
      const zip = new JSZip();

      const validExtensions = new Set(['.md', '.txt', '.org']);
      let addedCount = 0;

      for (const file of Array.from(files)) {
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        if (!validExtensions.has(ext)) {
          continue;
        }

        const content = await file.arrayBuffer();
        const relativePath = file.webkitRelativePath || file.name;
        zip.file(relativePath, content);
        addedCount++;
      }

      if (addedCount === 0) {
        toast.error(t('import.noValidFiles'));
        return;
      }

      const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
      const zipFile = new File([blob], 'folder-import.zip', { type: 'application/zip' });

      const result = await wikiService.importZip(zipFile, '.md,.txt,.org', true, agentScopeId);
      await finishImportResult(result, { kind: 'zip', zipFile });
    } catch (error) {
      console.error('Web folder import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImporting(false);
      if (webFolderInputRef.current) {
        webFolderInputRef.current.value = '';
      }
    }
  };

  const handleImportZip = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setIsImporting(true);
    try {
      const result = await wikiService.importZip(file, '.md,.txt,.org', true, agentScopeId);
      await finishImportResult(result, { kind: 'zip', zipFile: file });
    } catch (error) {
      console.error('ZIP import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImporting(false);
      if (zipInputRef.current) {
        zipInputRef.current.value = '';
      }
    }
  };

  const handleImportObsidianFolder = async () => {
    if (!isTauriEnv) {
      return;
    }
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, multiple: false, title: t('import.selectObsidianVault') });
      if (!selected) {
        return;
      }

      setIsImportingObsidian(true);
      const vaultPath = selected as string;
      const result = await wikiService.importObsidianFolder(vaultPath, true, agentScopeId);
      await finishImportResult(result, { kind: 'obsidian-folder', folderPath: vaultPath });
    } catch (error) {
      console.error('Obsidian folder import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImportingObsidian(false);
    }
  };

  const handleImportObsidianZip = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setIsImportingObsidian(true);
    try {
      const result = await wikiService.importObsidianZip(file, true, agentScopeId);
      await finishImportResult(result, { kind: 'obsidian-zip', zipFile: file });
    } catch (error) {
      console.error('Obsidian ZIP import failed:', error);
      toast.error(t('errors.importFailed'));
    } finally {
      setIsImportingObsidian(false);
      if (obsidianZipRef.current) {
        obsidianZipRef.current.value = '';
      }
    }
  };

  const dismissImportConflict = () => {
    setImportConflictOpen(false);
    setPendingImportRetry(null);
    setImportConflictPaths([]);
  };

  const keepSkippedImports = () => {
    toast.message(t('import.conflictSkippedToast', { count: importConflictPaths.length }));
    dismissImportConflict();
  };

  const dismissImportSecurity = () => {
    setImportSecurityOpen(false);
    setImportSecurityBlockedPaths([]);
    setImportSecurityRedactedPaths([]);
  };

  const handleUrlImportFinished = async (result: ImportUrlsResultResponse) => {
    await loadStats();
    bumpTreeSync();
    if (result.enqueued_count > 0) {
      toast.message(t('import.dedupScanStarted'));
      handleWikiTabChange('duplicateReview');
    }
  };

  const handleVideoImportFinished = async (result: ImportVideoResponse) => {
    await loadStats();
    bumpTreeSync();
    if (result.success && result.status !== 'skipped_conflict') {
      toast.message(t('import.dedupScanStarted'));
      handleWikiTabChange('duplicateReview');
    }
  };

  return {
    isTauriEnv,
    isImporting,
    isImportingObsidian,
    zipInputRef,
    obsidianZipRef,
    webFolderInputRef,
    handleImportFolder,
    handleWebFolderSelect,
    handleImportZip,
    handleImportObsidianFolder,
    handleImportObsidianZip,
    urlImportDialogOpen,
    setUrlImportDialogOpen,
    videoImportDialogOpen,
    setVideoImportDialogOpen,
    importConflictOpen,
    importConflictPaths,
    importSecurityOpen,
    importSecurityBlockedPaths,
    importSecurityRedactedPaths,
    dismissImportConflict,
    keepSkippedImports,
    retryImportWithSupersede,
    dismissImportSecurity,
    handleUrlImportFinished,
    handleVideoImportFinished,
  };
}

export type WikiImportController = ReturnType<typeof useWikiImport>;
