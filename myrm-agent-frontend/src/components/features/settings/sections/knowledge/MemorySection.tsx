'use client';

/**
 * [INPUT] @/store/memory + useConfigStore + useAuthStore (POS: 记忆数据 / 开关 / 登录态), ./memory-section/* (POS: 数据加载、导入导出、记忆操作与各区块组件), @/components/features/memory/* (POS: 记忆卡片、面板与对话框)
 * [OUTPUT] MemorySection: 设置页“记忆”面板（头部 + 工具栏 + 记忆开关 + 标签页内容 + 编辑 / 详情 / 新建 / 指南 / 分享对话框）
 * [POS] 记忆面板的编排层：只持有标签页与对话框开关状态，数据加载、导入导出、记忆操作分别交给 memory-section/ 下的 hook；记忆关闭时只显示开关，未登录时显示登录提示；支持 ?tab= 深链定位标签页。
 */

import { memo, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import LoginPrompt from '@/components/features/app-shell/login-prompt';
import MemoryCommandCenter from '@/components/features/memory/command-center/MemoryCommandCenter';
import MemoryClearAllDialog from '@/components/features/memory/dialogs/MemoryClearAllDialog';
import MemoryCreateDialog from '@/components/features/memory/dialogs/MemoryCreateDialog';
import MemoryDetailSheet from '@/components/features/memory/cards/MemoryDetailSheet';
import MemoryEditDialog from '@/components/features/memory/dialogs/MemoryEditDialog';
import { MemoryImportReviewDialog } from '@/components/features/memory/dialogs/MemoryImportReviewDialog';
import MemoryGuide from '@/components/features/memory/guides/MemoryGuide';
import MemoryContextPanel from '@/components/features/memory/insights/MemoryContextPanel';
import { MemoryDomainMeshPanel } from '@/components/features/memory/mesh';
import PendingMemoryList from '@/components/features/memory/pending/PendingMemoryList';
import ConversationRecallPanel from '@/components/features/memory/replay/ConversationRecallPanel';
import MemoryScopeHierarchyCard from '@/components/features/memory/cards/MemoryScopeHierarchyCard';
import MemorySettingsToggles from '@/components/features/memory/settings/MemorySettingsToggles';
import MemoryTabSwitcher, { type MemoryTab } from '@/components/features/memory/settings/MemoryTabSwitcher';
import ShareRulesDialog from '@/components/features/memory/dialogs/ShareRulesDialog';
import SharedContextPanel from '@/components/features/memory/shared-context/SharedContextPanel';
import MemoryStats from '@/components/features/memory/cards/MemoryStats';
import PreferenceStabilityCard from '@/components/features/memory/cards/PreferenceStabilityCard';
import TasteSummaryCard from '@/components/features/memory/cards/TasteSummaryCard';
import { isMemoryLabsEnabled } from '@/lib/memory/memoryLabs';
import { useMemoryStore, type Memory } from '@/store/memory';
import useAuthStore from '@/store/useAuthStore';
import useConfigStore from '@/store/useConfigStore';
import { MemoryAllTab } from './memory-section/MemoryAllTab';
import { MemoryHeader } from './memory-section/MemoryHeader';
import { MemoryToolbar } from './memory-section/MemoryToolbar';
import { MemoryTrashTab } from './memory-section/MemoryTrashTab';
import { useMemoryActions } from './memory-section/useMemoryActions';
import { useMemoryImportExport } from './memory-section/useMemoryImportExport';
import { useMemoryTabData } from './memory-section/useMemoryTabData';
import WorkingStateCard from './WorkingStateCard';

const MEMORY_TABS: readonly string[] = ['pending', 'all', 'context', 'shared', 'recall', 'trash'];

const isMemoryTab = (value: string): value is MemoryTab => MEMORY_TABS.includes(value);

const MemorySection = memo(() => {
  const t = useTranslations('memory');
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
    memoryEnableConversationSearch,
    setMemoryEnableConversationSearch,
    preCompactEnabled,
    setPreCompactEnabled,
    preCompactBudgetTokens,
    setPreCompactBudgetTokens,
  } = useConfigStore();

  const pendingCount = useMemoryStore((state) => state.pendingCount);
  const memoryTotal = useMemoryStore((state) => state.memoryPagination?.total);
  const archivedTotal = useMemoryStore((state) => state.archivedPagination?.total);
  const fetchMemories = useMemoryStore((state) => state.fetchMemories);

  const [activeMemoryTab, setActiveMemoryTab] = useState<MemoryTab>('pending');
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [detailMemory, setDetailMemory] = useState<Memory | null>(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showMemoryGuide, setShowMemoryGuide] = useState(false);
  const [showShareRules, setShowShareRules] = useState(false);

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab && isMemoryTab(tab)) {
      setActiveMemoryTab(tab);
    }
  }, [searchParams]);

  const { searchInput, setSearchInput, availableTags, isRefreshing, refresh } = useMemoryTabData(
    activeMemoryTab,
    isLoggedIn && authInitialized,
  );
  const importExport = useMemoryImportExport(fetchMemories);
  const actions = useMemoryActions();
  const { pendingImport } = importExport;

  return (
    <div className="space-y-6">
      <MemoryImportReviewDialog
        open={pendingImport !== null}
        dryRun={pendingImport?.dryRun ?? null}
        expiresAt={pendingImport?.expiresAt ?? null}
        importing={importExport.isImporting}
        onOpenChange={importExport.handleImportReviewOpenChange}
        onConfirm={importExport.handleConfirmImport}
      />
      <div className="flex items-start justify-between gap-3">
        <MemoryHeader enableMemory={enableMemory} onOpenGuide={() => setShowMemoryGuide(true)} />
        {isLoggedIn && enableMemory && (
          <MemoryToolbar
            importExport={importExport}
            isRefreshing={isRefreshing}
            onRefresh={refresh}
            onShareRules={() => setShowShareRules(true)}
            onCreate={() => setShowCreateDialog(true)}
            onClearAll={() => actions.setShowClearConfirm(true)}
          />
        )}
      </div>

      <MemorySettingsToggles
        enableMemory={enableMemory}
        setEnableMemory={setEnableMemory}
        memoryRequireConfirmation={memoryRequireConfirmation}
        setMemoryRequireConfirmation={setMemoryRequireConfirmation}
        enableMemoryAutoExtraction={enableMemoryAutoExtraction}
        setEnableMemoryAutoExtraction={setEnableMemoryAutoExtraction}
        memoryEnableConversationSearch={memoryEnableConversationSearch}
        setMemoryEnableConversationSearch={setMemoryEnableConversationSearch}
        preCompactEnabled={preCompactEnabled}
        setPreCompactEnabled={setPreCompactEnabled}
        preCompactBudgetTokens={preCompactBudgetTokens}
        setPreCompactBudgetTokens={setPreCompactBudgetTokens}
      />

      {!enableMemory ? null : !isLoggedIn ? (
        <LoginPrompt title={t('loginRequired')} description={t('loginRequiredDesc')} />
      ) : (
        <>
          <WorkingStateCard />
          <MemoryScopeHierarchyCard />
          {isMemoryLabsEnabled() ? <MemoryCommandCenter /> : null}
          <MemoryDomainMeshPanel />
          <MemoryStats />
          <TasteSummaryCard />
          <PreferenceStabilityCard />

          <MemoryTabSwitcher
            activeTab={activeMemoryTab}
            pendingCount={pendingCount}
            totalCount={memoryTotal}
            archivedCount={archivedTotal}
            onChange={setActiveMemoryTab}
          />

          {activeMemoryTab === 'pending' && <PendingMemoryList showBatchActions />}
          {activeMemoryTab === 'context' && <MemoryContextPanel />}
          {activeMemoryTab === 'shared' && <SharedContextPanel />}
          {activeMemoryTab === 'recall' && <ConversationRecallPanel />}
          {activeMemoryTab === 'trash' && <MemoryTrashTab />}
          {activeMemoryTab === 'all' && (
            <MemoryAllTab
              searchInput={searchInput}
              onSearchInputChange={setSearchInput}
              availableTags={availableTags}
              actions={actions}
              onOpenDetail={setDetailMemory}
              onEdit={setEditingMemory}
            />
          )}
        </>
      )}

      <MemoryEditDialog
        memory={editingMemory}
        open={!!editingMemory}
        onOpenChange={(v) => {
          if (!v) {
            setEditingMemory(null);
          }
        }}
      />

      <MemoryClearAllDialog
        open={actions.showClearConfirm}
        onOpenChange={actions.setShowClearConfirm}
        isClearing={actions.isClearing}
        onConfirm={actions.handleClearAll}
      />

      <MemoryCreateDialog open={showCreateDialog} onOpenChange={setShowCreateDialog} />

      <MemoryDetailSheet
        memory={detailMemory}
        open={!!detailMemory}
        onOpenChange={(v) => {
          if (!v) {
            setDetailMemory(null);
          }
        }}
      />

      <MemoryGuide open={showMemoryGuide} onOpenChange={setShowMemoryGuide} />

      <ShareRulesDialog open={showShareRules} onOpenChange={setShowShareRules} />
    </div>
  );
});

MemorySection.displayName = 'MemorySection';

export default MemorySection;
