/**
 * [INPUT]
 * ./wiki-section/* (POS: 范围、导航、目的、总览数据、问答、维护、导入各层 hook 与各卡片组件)
 * ./Wiki*.tsx、./ima/ImaSourceCard、./SecondBrainSetupCard 等 (POS: 概念 / 待审 / 重复审核 / 队列面板与总览页的外部来源卡)
 *
 * [OUTPUT]
 * WikiSection: Wiki 知识库配置主面板，支持概念/审核/队列/原始文件树浏览与导入管理。
 *
 * [POS]
 * Settings 知识库模块核心面板组件。编排 Wiki 知识库总览、原始文件、审核队列与统计；状态与动作在 wiki-section/ 的各层 hook，界面在其卡片组件。
 */
'use client';

import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/primitives/tabs';
import { WikiConceptsList } from './WikiConceptsList';
import { WikiPendingEdits } from './WikiPendingEdits';
import { WikiDuplicateReviewPanel } from './WikiDuplicateReviewPanel';
import { WikiIgnorePanel } from './WikiIgnorePanel';
import { WikiQueuePanel } from './WikiQueuePanel';
import { WikiAgentScopeProvider } from './WikiAgentScopeContext';
import ImaSourceCard from './ima/ImaSourceCard';
import WikiSourceSyncPanel from './WikiSourceSyncPanel';
import SecondBrainSetupCard from './SecondBrainSetupCard';
import { ObsidianVaultActions } from './ObsidianVaultActions';
import MeetingNotesImportCard from './MeetingNotesImportCard';
import DailyReviewCard from './DailyReviewCard';
import { WikiLayersLedgerPanel } from './wiki/WikiLayersLedgerPanel';
import { useWikiImport } from './wiki-section/useWikiImport';
import { useWikiMaintenance } from './wiki-section/useWikiMaintenance';
import { useWikiOverviewData } from './wiki-section/useWikiOverviewData';
import { useWikiPurpose } from './wiki-section/useWikiPurpose';
import { useWikiQuery } from './wiki-section/useWikiQuery';
import { useWikiScope } from './wiki-section/useWikiScope';
import { useWikiTabs } from './wiki-section/useWikiTabs';
import { WikiActionsCard } from './wiki-section/WikiActionsCard';
import { WikiBatchImportCard } from './wiki-section/WikiBatchImportCard';
import { WikiImportDialogs } from './wiki-section/WikiImportDialogs';
import { WikiObsidianImportCard } from './wiki-section/WikiObsidianImportCard';
import { WikiPurposeCard } from './wiki-section/WikiPurposeCard';
import { WikiQueryCard } from './wiki-section/WikiQueryCard';
import { WikiScopeHeader } from './wiki-section/WikiScopeHeader';
import { WikiStatsCard } from './wiki-section/WikiStatsCard';

export function WikiSection() {
  const router = useRouter();
  const t = useTranslations('settings.wiki');
  const scope = useWikiScope();
  const { agentScopeId } = scope;
  const tabs = useWikiTabs();
  const { activeTab, handleWikiTabChange } = tabs;
  const purpose = useWikiPurpose(agentScopeId);
  const overview = useWikiOverviewData(agentScopeId, activeTab);
  const { stats } = overview;
  const wikiQuery = useWikiQuery(agentScopeId, scope.evidenceContextKey);
  const maintenance = useWikiMaintenance({ agentScopeId, overview, handleWikiTabChange });
  const imports = useWikiImport({
    agentScopeId,
    overview,
    handleWikiTabChange,
    goToKnowledgeGraph: scope.goToKnowledgeGraph,
  });

  const handleVaultMutated = () => {
    void overview.loadStats();
  };

  return (
    <WikiAgentScopeProvider
      agentScopeId={agentScopeId}
      scopeRevision={scope.scopeRevision}
      scopeLabel={scope.scopeLabel}
    >
      <div className="space-y-6" data-testid="wiki-settings-shell">
        <WikiScopeHeader
          agentScopeId={agentScopeId}
          agents={scope.agents}
          agentsLoading={scope.agentsLoading}
          onScopeChange={scope.handleAgentScopeChange}
        />

        <Tabs value={activeTab} onValueChange={handleWikiTabChange} className="flex flex-col flex-1 min-h-0 space-y-6">
          <TabsList className="flex flex-wrap h-auto w-full bg-secondary/50 backdrop-blur-sm p-1 rounded-xl border border-border/40 gap-1">
            <TabsTrigger value="overview">{t('tabs.overview')}</TabsTrigger>
            <TabsTrigger value="concepts">{t('tabs.concepts')}</TabsTrigger>
            <TabsTrigger value="pendingEdits">{t('tabs.pendingEdits')}</TabsTrigger>
            <TabsTrigger value="duplicateReview" data-testid="wiki-dedup-tab">
              {t('tabs.duplicateReview')}
            </TabsTrigger>
            <TabsTrigger value="queue">{t('tabs.queue')}</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-6">
            <WikiLayersLedgerPanel onOpenConcept={tabs.openConcept} />

            <SecondBrainSetupCard
              onApplied={(agentId) => {
                handleVaultMutated();
                scope.handleAgentScopeChange(agentId);
              }}
              onGoToImport={() =>
                document.getElementById('wiki-obsidian-import')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }
              onGoToProviders={() => router.push('/settings/models')}
              onGoToDuplicateReview={tabs.handleOpenDuplicateReview}
              onGoToGraph={scope.goToKnowledgeGraph}
            />

            <WikiSourceSyncPanel onGoToIntegrations={() => router.push('/settings/credentials')} />

            <ImaSourceCard onGoToDuplicateReview={tabs.handleOpenDuplicateReview} />

            <WikiPurposeCard {...purpose} />

            <WikiStatsCard agentScopeId={agentScopeId} overview={overview} maintenance={maintenance} tabs={tabs} />

            <ObsidianVaultActions
              agentScopeId={agentScopeId}
              wikiPath={stats?.wiki_path}
              vaultReady={stats?.vault_ready ?? false}
              obsidianLaunchAvailable={stats?.obsidian_launch_available ?? false}
              vaultGitEnabled={stats?.vault_git_enabled ?? false}
              vaultGitInitialized={stats?.vault_git_initialized ?? false}
              vaultGitLastCommit={stats?.vault_git_last_commit ?? null}
            />

            <MeetingNotesImportCard />

            <DailyReviewCard />

            <WikiQueryCard
              wikiQuery={wikiQuery}
              agentScopeId={agentScopeId}
              evidenceContextKey={scope.evidenceContextKey}
            />

            <WikiActionsCard
              maintenance={maintenance}
              overview={overview}
              onViewQueue={() => handleWikiTabChange('queue')}
            />

            <WikiBatchImportCard {...imports} />

            <WikiIgnorePanel />

            <WikiObsidianImportCard {...imports} />
          </TabsContent>

          <TabsContent value="concepts" className="space-y-6 flex flex-col flex-1 min-h-0">
            <WikiConceptsList
              key={`${agentScopeId ?? 'default'}-${scope.scopeRevision}`}
              treeSyncNonce={overview.treeSyncNonce}
              agentScopeId={agentScopeId}
              highlightConceptPath={tabs.conceptPathFromUrl}
              onVaultMutated={handleVaultMutated}
            />
          </TabsContent>

          <TabsContent value="pendingEdits" className="space-y-6">
            <WikiPendingEdits
              agentScopeId={agentScopeId}
              scopeLabel={scope.scopeLabel}
              initialFilter={tabs.pendingEditsInitialFilter}
              onVaultMutated={handleVaultMutated}
            />
          </TabsContent>

          <TabsContent value="duplicateReview" className="space-y-6">
            <WikiDuplicateReviewPanel
              agentScopeId={agentScopeId}
              scopeLabel={scope.scopeLabel}
              onVaultMutated={handleVaultMutated}
            />
          </TabsContent>

          <TabsContent value="queue" className="space-y-6">
            <WikiQueuePanel
              agentScopeId={agentScopeId}
              scopeLabel={scope.scopeLabel}
              liveIngestConnected={overview.ingestLive}
              liveIngestSnapshot={overview.ingestSnapshot}
            />
          </TabsContent>
        </Tabs>
        <WikiImportDialogs agentScopeId={agentScopeId} imports={imports} />
      </div>
    </WikiAgentScopeProvider>
  );
}
