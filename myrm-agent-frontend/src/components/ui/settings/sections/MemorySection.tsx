'use client';

import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import {
  IconArrowDown,
  IconArrowUp,
  IconArrowUpDown,
  IconDownload,
  IconInbox,
  IconLoader,
  IconPlus,
  IconRefresh,
  IconSearch,
  IconTrash,
  IconUpload,
  IconBook,
} from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import useConfigStore from '@/store/useConfigStore';
import useAuthStore from '@/store/useAuthStore';
import { useMemoryStore, type MemoryType, type Memory } from '@/store/memory';
import { restoreMemory as apiRestoreMemory } from '@/services/memory';
import MemoryClearAllDialog from '@/components/ui/memory/MemoryClearAllDialog';
import MemorySettingsToggles from '@/components/ui/memory/MemorySettingsToggles';
import MemoryTabSwitcher, { type MemoryTab } from '@/components/ui/memory/MemoryTabSwitcher';
import {
  PendingMemoryList,
  MemoryCard,
  MemoryTypeIcon,
  MemoryEditDialog,
  MemoryCreateDialog,
  MemoryDetailSheet,
  MemoryStats,
} from '@/components/ui/memory';
import MemoryGuide from '@/components/ui/memory/MemoryGuide';
import MemoryCommandCenter from '@/components/ui/memory/MemoryCommandCenter';
import TasteSummaryCard from '@/components/ui/memory/TasteSummaryCard';
import PreferenceStabilityCard from '@/components/ui/memory/PreferenceStabilityCard';
import SharedContextPanel from '@/components/ui/memory/SharedContextPanel';
import MemoryContextPanel from '@/components/ui/memory/MemoryContextPanel';
import ConversationRecallPanel from '@/components/ui/memory/ConversationRecallPanel';
import MemoryTrashPanel from '@/components/ui/memory/MemoryTrashPanel';
import { MemoryImportReviewDialog } from '@/components/ui/memory/MemoryImportReviewDialog';
import LoginPrompt from '@/components/ui/login-prompt';
import { toast } from '@/hooks/useToast';
import { exportMemories, updateMemoryStatus } from '@/services/memory';
import { confirmImportMemories, dryRunImportMemories, type MemoryImportDryRunResult } from '@/services/memoryArchive';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

const MEMORY_TYPES: (MemoryType | null)[] = [
  null,
  'profile',
  'semantic',
  'episodic',
  'procedural',
  'conversation',
  'claim',
  'task_digest',
];

const MEMORY_TABS: MemoryTab[] = ['pending', 'all', 'context', 'shared', 'recall', 'trash'];

const MemorySection = memo(() => {
  const t = useTranslations('memory');
  const tCommon = useTranslations('common');
  const searchParams = useSearchParams();

  const { user, isInitialized: authInitialized } = useAuthStore();
  const isLoggedIn = !!user;

  const {
    enableMemory,
    setEnableMemory,
    memoryRequireConfirmation,
    setMemoryRequireConfirmation,
    enableMemoryAutoExtraction,
    setEnableMemoryAutoExtraction,
    preCompactEnabled,
    setPreCompactEnabled,
    preCompactBudgetTokens,
    setPreCompactBudgetTokens,
  } = useConfigStore();

  const {
    pendingCount,
    memories,
    memoriesLoading,
    memoryPagination,
    memoryTypeFilter,
    memorySearchQuery,
    fetchPendingMemories,
    fetchMemories,
    loadMoreMemories,
    setMemoryTypeFilter,
    setMemorySearchQuery,
    deleteMemory,
    deleteAllMemories,
    memorySortBy,
    setMemorySortBy,
    memorySortOrder,
    setMemorySortOrder,
    archivedMemories,
    archivedLoading,
    archivedPagination,
    fetchArchivedMemories,
    restoreMemory,
    purgeMemory,
  } = useMemoryStore();

  const [activeMemoryTab, setActiveMemoryTab] = useState<MemoryTab>('pending');
  const [searchInput, setSearchInput] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab && MEMORY_TABS.includes(tab as MemoryTab)) {
      setActiveMemoryTab(tab as MemoryTab);
    }
  }, [searchParams]);
  const [isExporting, setIsExporting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [detailMemory, setDetailMemory] = useState<Memory | null>(null);
  const [importDryRun, setImportDryRun] = useState<MemoryImportDryRunResult | null>(null);
  const [importDryRunId, setImportDryRunId] = useState<string | null>(null);
  const [importPayloadHash, setImportPayloadHash] = useState<string | null>(null);
  const [importExpiresAt, setImportExpiresAt] = useState<string | null>(null);
  const [showImportReview, setShowImportReview] = useState(false);
  const [showMemoryGuide, setShowMemoryGuide] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isLoggedIn && authInitialized) fetchPendingMemories();
  }, [isLoggedIn, authInitialized, fetchPendingMemories]);

  useEffect(() => {
    if (activeMemoryTab === 'all' && isLoggedIn && authInitialized) fetchMemories();
    if (activeMemoryTab === 'trash' && isLoggedIn && authInitialized) fetchArchivedMemories();
  }, [activeMemoryTab, isLoggedIn, authInitialized, fetchMemories, fetchArchivedMemories]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== memorySearchQuery && activeMemoryTab === 'all') {
        setMemorySearchQuery(searchInput);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput, memorySearchQuery, setMemorySearchQuery, activeMemoryTab]);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      if (activeMemoryTab === 'pending') await fetchPendingMemories();
      else if (activeMemoryTab === 'trash') await fetchArchivedMemories();
      else await fetchMemories();
    } finally {
      setIsRefreshing(false);
    }
  }, [activeMemoryTab, fetchPendingMemories, fetchMemories, fetchArchivedMemories]);

  const handleDelete = useCallback(
    async (id: string, memoryType: MemoryType) => {
      const isSoftDeletable = memoryType === 'semantic' || memoryType === 'episodic';
      try {
        await deleteMemory(id, memoryType);
        if (isSoftDeletable) {
          toast({
            title: t('deleteSuccess'),
            description: t('trash.undoHint'),
            action: {
              label: t('trash.undo'),
              onClick: async () => {
                try {
                  await apiRestoreMemory(id);
                  await fetchMemories();
                  toast({ title: t('trash.restoreSuccess') });
                } catch {
                  toast({ title: t('trash.restoreFailed'), variant: 'destructive' });
                }
              },
            },
          });
        } else {
          toast({ title: t('deleteSuccess'), description: t('deleteSuccessDesc') });
        }
      } catch (error) {
        toast({
          title: t('deleteFailed'),
          description: error instanceof Error ? error.message : t('unknownError'),
          variant: 'destructive',
        });
      }
    },
    [deleteMemory, fetchMemories, t],
  );

  const handleExport = useCallback(async () => {
    setIsExporting(true);
    try {
      const result = await exportMemories();
      if (result.total_count === 0) {
        toast({ title: t('noMemoriesToExport'), variant: 'destructive' });
        return;
      }
      const exportPayload = { version: result.version, data: result.data };
      const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `memories-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast({
        title: t('exportSuccess'),
        description: t('exportSuccessDesc', { count: result.total_count }),
      });
    } catch (error) {
      toast({
        title: t('exportFailed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsExporting(false);
    }
  }, [t]);

  const handleImportFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      const MAX_IMPORT_SIZE_MB = 50;
      if (file.size > MAX_IMPORT_SIZE_MB * 1024 * 1024) {
        toast({
          title: t('importFailed'),
          description: t('importFileTooLarge', { maxMb: MAX_IMPORT_SIZE_MB }),
          variant: 'destructive',
        });
        if (importInputRef.current) importInputRef.current.value = '';
        return;
      }

      setIsImporting(true);
      try {
        const text = await file.text();
        let payload: Record<string, unknown>;

        if (file.name.endsWith('.jsonl')) {
          const rawLines = text.split('\n').filter((line) => line.trim());
          const lines: unknown[] = [];
          for (const line of rawLines) {
            try {
              lines.push(JSON.parse(line));
            } catch {
              // skip malformed lines (streaming truncation, encoding issues, etc.)
            }
          }
          if (lines.length === 0) {
            throw new Error(t('importJsonlNoValidLines'));
          }
          payload = { jsonl_lines: lines, _source_hint: 'claude_code_jsonl' };
        } else {
          payload = JSON.parse(text) as Record<string, unknown>;
        }

        const source = file.name.endsWith('.jsonl') ? 'claude_code_jsonl' : 'auto';
        const dryRun = await dryRunImportMemories(payload, source);
        setImportDryRun(dryRun.result);
        setImportDryRunId(dryRun.dry_run_id);
        setImportPayloadHash(dryRun.payload_hash);
        setImportExpiresAt(dryRun.expires_at);
        setShowImportReview(true);
      } catch (error) {
        toast({
          title: t('importFailed'),
          description: error instanceof Error ? error.message : t('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setIsImporting(false);
        if (importInputRef.current) importInputRef.current.value = '';
      }
    },
    [t],
  );

  const handleConfirmImport = useCallback(async () => {
    if (!importDryRunId) return;
    setIsImporting(true);
    try {
      const result = await confirmImportMemories(importDryRunId, true);
      toast({
        title: t('importSuccess'),
        description: t('importSuccessDesc', { count: result.total_imported }),
      });
      setShowImportReview(false);
      setImportDryRun(null);
      setImportDryRunId(null);
      setImportPayloadHash(null);
      setImportExpiresAt(null);
      await fetchMemories();
    } catch (error) {
      toast({
        title: t('importFailed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsImporting(false);
    }
  }, [fetchMemories, importDryRunId, t]);

  const handleImportReviewOpenChange = useCallback((open: boolean) => {
    setShowImportReview(open);
    if (!open) {
      setImportDryRun(null);
      setImportDryRunId(null);
      setImportPayloadHash(null);
      setImportExpiresAt(null);
    }
  }, []);

  const handleToggleDisable = useCallback(
    async (mem: Memory) => {
      const newStatus = mem.status === 'disabled' ? 'active' : 'disabled';
      try {
        await updateMemoryStatus(mem.id, newStatus);
        await fetchMemories();
        toast({
          title: newStatus === 'disabled' ? t('disableSuccess') : t('enableSuccess'),
          description: newStatus === 'disabled' ? t('disableSuccessDesc') : t('enableSuccessDesc'),
        });
      } catch (error) {
        toast({
          title: t('statusUpdateFailed'),
          description: error instanceof Error ? error.message : t('unknownError'),
          variant: 'destructive',
        });
      }
    },
    [fetchMemories, t],
  );

  const handleChatFromMemory = useCallback((mem: Memory) => {
    const chatUrl = `/?initialMessage=${encodeURIComponent(mem.content)}`;
    window.open(chatUrl, '_self');
  }, []);

  const handleClearAll = useCallback(async () => {
    setIsClearing(true);
    try {
      await deleteAllMemories();
      toast({ title: t('clearAllSuccess'), description: t('clearAllSuccessDesc') });
      setShowClearConfirm(false);
    } catch (error) {
      toast({
        title: t('clearAllFailed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsClearing(false);
    }
  }, [deleteAllMemories, t]);

  return (
    <div className="space-y-6">
      <MemoryImportReviewDialog
        open={showImportReview}
        dryRun={importDryRun}
        payloadHash={importPayloadHash}
        expiresAt={importExpiresAt}
        importing={isImporting}
        onOpenChange={handleImportReviewOpenChange}
        onConfirm={handleConfirmImport}
      />
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold text-foreground">{t('title')}</h2>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => setShowMemoryGuide(true)}
                  aria-label={t('guide.openGuideHint')}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border border-border/60',
                    'bg-accent/40 px-2.5 py-1 text-xs font-medium text-muted-foreground',
                    'transition-colors duration-200',
                    'hover:border-primary/30 hover:bg-primary/10 hover:text-foreground',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
                  )}
                >
                  <IconBook className="h-3.5 w-3.5 shrink-0" />
                  <span className="hidden sm:inline">{t('guide.openGuide')}</span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-xs text-xs">
                {t('guide.openGuideHint')}
              </TooltipContent>
            </Tooltip>
          </div>
          <p className="text-sm text-muted-foreground">{t('description')}</p>
        </div>
        {isLoggedIn && enableMemory && (
          <div className="flex items-center gap-1">
            <input
              ref={importInputRef}
              type="file"
              accept=".json,.jsonl"
              onChange={handleImportFile}
              className="hidden"
            />
            <button
              onClick={() => importInputRef.current?.click()}
              disabled={isImporting}
              title={t('import')}
              className={cn(
                'p-2 rounded-lg transition-colors',
                'hover:bg-accent',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {isImporting ? (
                <IconLoader className="w-[18px] h-[18px] animate-spin text-muted-foreground" />
              ) : (
                <IconUpload className="w-[18px] h-[18px] text-muted-foreground" />
              )}
            </button>
            <button
              onClick={handleExport}
              disabled={isExporting}
              title={t('export')}
              className={cn(
                'p-2 rounded-lg transition-colors',
                'hover:bg-accent',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {isExporting ? (
                <IconLoader className="w-[18px] h-[18px] animate-spin text-muted-foreground" />
              ) : (
                <IconDownload className="w-[18px] h-[18px] text-muted-foreground" />
              )}
            </button>
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              title={t('retry')}
              className={cn(
                'p-2 rounded-lg transition-colors',
                'hover:bg-accent',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              <IconRefresh className={cn('w-[18px] h-[18px] text-muted-foreground', isRefreshing && 'animate-spin')} />
            </button>
            <button
              onClick={() => setShowCreateDialog(true)}
              title={t('createDialog.title')}
              className={cn('p-2 rounded-lg transition-colors', 'hover:bg-accent')}
            >
              <IconPlus className="w-[18px] h-[18px] text-muted-foreground" />
            </button>
            <button
              onClick={() => setShowClearConfirm(true)}
              title={t('clearAll')}
              className={cn('p-2 rounded-lg transition-colors', 'hover:bg-destructive/10')}
            >
              <IconTrash className="w-[18px] h-[18px] text-muted-foreground hover:text-destructive" />
            </button>
          </div>
        )}
      </div>

      <MemorySettingsToggles
        enableMemory={enableMemory}
        setEnableMemory={setEnableMemory}
        memoryRequireConfirmation={memoryRequireConfirmation}
        setMemoryRequireConfirmation={setMemoryRequireConfirmation}
        enableMemoryAutoExtraction={enableMemoryAutoExtraction}
        setEnableMemoryAutoExtraction={setEnableMemoryAutoExtraction}
        preCompactEnabled={preCompactEnabled}
        setPreCompactEnabled={setPreCompactEnabled}
        preCompactBudgetTokens={preCompactBudgetTokens}
        setPreCompactBudgetTokens={setPreCompactBudgetTokens}
      />

      {!enableMemory ? null : !isLoggedIn ? (
        <LoginPrompt title={t('loginRequired')} description={t('loginRequiredDesc')} />
      ) : (
        <>
          <MemoryCommandCenter />
          <MemoryStats />
          <TasteSummaryCard />
          <PreferenceStabilityCard />

          <MemoryTabSwitcher
            activeTab={activeMemoryTab}
            pendingCount={pendingCount}
            totalCount={memoryPagination?.total}
            archivedCount={archivedPagination?.total}
            onChange={setActiveMemoryTab}
          />

          {activeMemoryTab === 'pending' && <PendingMemoryList showBatchActions />}

          {activeMemoryTab === 'context' && <MemoryContextPanel />}

          {activeMemoryTab === 'shared' && <SharedContextPanel />}

          {activeMemoryTab === 'recall' && <ConversationRecallPanel />}

          {activeMemoryTab === 'trash' && (
            <MemoryTrashPanel
              memories={archivedMemories}
              loading={archivedLoading}
              pagination={archivedPagination}
              onRestore={async (id) => {
                try {
                  await restoreMemory(id);
                  toast({ title: t('trash.restoreSuccess') });
                } catch {
                  toast({ title: t('trash.restoreFailed'), variant: 'destructive' });
                }
              }}
              onPurge={async (id) => {
                try {
                  await purgeMemory(id);
                  toast({ title: t('trash.purgeSuccess') });
                } catch {
                  toast({ title: t('trash.purgeFailed'), variant: 'destructive' });
                }
              }}
              onLoadMore={() => {
                if (archivedPagination?.has_next) {
                  fetchArchivedMemories(archivedPagination.page + 1);
                }
              }}
            />
          )}

          {activeMemoryTab === 'all' && (
            <div className="space-y-4">
              {/* Search & filter */}
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                  <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    placeholder={t('searchPlaceholder')}
                    className={cn(
                      'w-full pl-9 pr-4 py-2.5 rounded-lg',
                      'bg-accent/50 border border-border/50',
                      'text-sm text-foreground placeholder:text-muted-foreground/50',
                      'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                      'transition-all duration-200',
                    )}
                  />
                </div>
                <div className="flex items-center gap-1 p-1 bg-accent/50 rounded-lg overflow-x-auto">
                  {MEMORY_TYPES.map((type) => {
                    const button = (
                      <button
                        key={type ?? 'all'}
                        onClick={() => setMemoryTypeFilter(type)}
                        className={cn(
                          'px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200',
                          'flex items-center gap-1.5 whitespace-nowrap',
                          memoryTypeFilter === type
                            ? 'bg-background text-foreground'
                            : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        {type ? (
                          <>
                            <MemoryTypeIcon type={type} size={12} />
                            <span className="hidden sm:inline">{t(`types.${type}`)}</span>
                          </>
                        ) : (
                          t('filterAll')
                        )}
                      </button>
                    );

                    if (!type) {
                      return button;
                    }

                    return (
                      <Tooltip key={type}>
                        <TooltipTrigger asChild>{button}</TooltipTrigger>
                        <TooltipContent side="bottom" className="max-w-[280px] space-y-1.5">
                          <div className="font-medium text-foreground">{t(`types.${type}`)}</div>
                          <div className="text-muted-foreground">{t(`typeTooltips.${type}.description`)}</div>
                          <div className="text-xs text-muted-foreground/80 pt-1 border-t border-border/50">
                            {t(`typeTooltips.${type}.example`)}
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
                </div>
              </div>

              {/* Sort */}
              <div className="flex items-center gap-2">
                <IconArrowUpDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                <select
                  value={memorySortBy}
                  onChange={(e) => setMemorySortBy(e.target.value as typeof memorySortBy)}
                  className={cn(
                    'px-2 py-1.5 rounded-full text-xs font-medium',
                    'bg-accent/50 border border-border/50',
                    'text-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-primary/20',
                  )}
                >
                  <option value="created_at">{t('createdAt')}</option>
                  <option value="updated_at">{t('updatedAt')}</option>
                  <option value="importance">{t('importance')}</option>
                </select>
                <button
                  onClick={() => setMemorySortOrder(memorySortOrder === 'desc' ? 'asc' : 'desc')}
                  className="p-1.5 rounded-full hover:bg-accent transition-colors"
                  title={memorySortOrder === 'desc' ? 'Descending' : 'Ascending'}
                >
                  {memorySortOrder === 'desc' ? (
                    <IconArrowDown className="w-3.5 h-3.5 text-muted-foreground" />
                  ) : (
                    <IconArrowUp className="w-3.5 h-3.5 text-muted-foreground" />
                  )}
                </button>
              </div>

              {/* Memory list */}
              {memoriesLoading && memories.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <IconLoader className="h-8 w-8 animate-spin text-primary/50" />
                  <p className="mt-3 text-sm text-muted-foreground">{t('loading')}</p>
                </div>
              ) : memories.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16">
                  <div className="relative">
                    <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-full" />
                    <div className="relative bg-accent/50 p-4 rounded-2xl">
                      <IconInbox className="h-10 w-10 text-muted-foreground/50" />
                    </div>
                  </div>
                  <p className="mt-4 text-sm font-medium text-foreground">{t('noMemories')}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{t('noMemoriesDesc')}</p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {memories.map((memory) => (
                      <MemoryCard
                        key={memory.id}
                        memory={memory}
                        variant="confirmed"
                        onClick={() => setDetailMemory(memory)}
                        onEdit={() => setEditingMemory(memory)}
                        onDelete={() => handleDelete(memory.id, memory.memory_type as MemoryType)}
                        onToggleDisable={() => handleToggleDisable(memory)}
                        onChatFromMemory={() => handleChatFromMemory(memory)}
                      />
                    ))}
                  </div>
                  {memoryPagination?.has_next && (
                    <div className="flex justify-center pt-4">
                      <button
                        onClick={loadMoreMemories}
                        disabled={memoriesLoading}
                        className={cn(
                          'flex items-center gap-2 px-6 py-2.5 rounded-lg',
                          'text-sm font-medium transition-all duration-200',
                          'border border-border/50 hover:border-border',
                          'text-muted-foreground hover:text-foreground',
                          'hover:bg-accent',
                          'disabled:opacity-50 disabled:cursor-not-allowed',
                        )}
                      >
                        {memoriesLoading ? (
                          <>
                            <IconLoader className="w-3.5 h-3.5 animate-spin" />
                            {t('loading')}
                          </>
                        ) : (
                          tCommon('loadMore')
                        )}
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}

      {/* Dialogs */}
      <MemoryEditDialog
        memory={editingMemory}
        open={!!editingMemory}
        onOpenChange={(v) => {
          if (!v) setEditingMemory(null);
        }}
      />

      <MemoryClearAllDialog
        open={showClearConfirm}
        onOpenChange={setShowClearConfirm}
        isClearing={isClearing}
        onConfirm={handleClearAll}
      />

      <MemoryCreateDialog open={showCreateDialog} onOpenChange={setShowCreateDialog} />

      <MemoryDetailSheet
        memory={detailMemory}
        open={!!detailMemory}
        onOpenChange={(v) => {
          if (!v) setDetailMemory(null);
        }}
      />

      <MemoryGuide open={showMemoryGuide} onOpenChange={setShowMemoryGuide} />
    </div>
  );
});

MemorySection.displayName = 'MemorySection';

export default MemorySection;
