'use client';

/**
 * [INPUT] ./useWikiOverviewData::WikiOverviewData (POS: 统计、健康报告与原文树), ./useWikiMaintenance + ./useWikiTabs (POS: 重新编译 / 修复页面类型动作与跨页签跳转), ../WikiHealthIssuesSection + ../wiki/WikiRawSourceTree (POS: 健康问题与原文树)
 * [OUTPUT] WikiStatsCard: “知识库统计”卡: 未加载时给出加载按钮, 加载中显示占位, 加载后依次显示徽标、健康问题、认知索引三格、概念 / 文章 / 原文计数与原文树
 * [POS] 总览页的统计卡, 只负责展示与转发动作; 原文树删除后静默刷新。
 */

import { useLocale, useTranslations } from 'next-intl';
import { IconDatabase } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { WikiHealthIssuesSection } from '../WikiHealthIssuesSection';
import { WikiRawSourceTree } from '../wiki/WikiRawSourceTree';
import type { WikiMaintenanceController } from './useWikiMaintenance';
import type { WikiOverviewData } from './useWikiOverviewData';
import type { WikiTabsController } from './useWikiTabs';
import { WikiStatsBadges } from './WikiStatsBadges';
import { formatCognitiveUpdatedAt } from './wikiStatsFormat';

interface WikiStatsCardProps {
  agentScopeId: string | null;
  overview: Pick<
    WikiOverviewData,
    | 'stats'
    | 'isLoadingStats'
    | 'loadStats'
    | 'healthReport'
    | 'isLoadingHealthReport'
    | 'healthReportLoadError'
    | 'healthReportExpanded'
    | 'setHealthReportExpanded'
    | 'loadHealthReport'
    | 'rawTreeData'
    | 'isLoadingRawTree'
    | 'refreshIngestTreesSilently'
    | 'synthesisPendingCount'
    | 'duplicateGroupsPending'
    | 'dedupBlocksCompile'
  >;
  maintenance: Pick<
    WikiMaintenanceController,
    'isCompiling' | 'handleCompile' | 'isRepairingTypes' | 'handleRepairPageTypes'
  >;
  tabs: Pick<
    WikiTabsController,
    | 'rawPathFromUrl'
    | 'navigateToHealthIssue'
    | 'handleOpenSynthesisPending'
    | 'handleOpenDuplicateReview'
    | 'handleWikiTabChange'
  >;
}

export function WikiStatsCard({ agentScopeId, overview, maintenance, tabs }: WikiStatsCardProps) {
  const t = useTranslations('settings.wiki');
  const locale = useLocale();
  const {
    stats,
    isLoadingStats,
    loadStats,
    healthReport,
    isLoadingHealthReport,
    healthReportLoadError,
    healthReportExpanded,
    setHealthReportExpanded,
    loadHealthReport,
    rawTreeData,
    isLoadingRawTree,
    refreshIngestTreesSilently,
    synthesisPendingCount,
    duplicateGroupsPending,
    dedupBlocksCompile,
  } = overview;
  const { isCompiling, handleCompile, isRepairingTypes, handleRepairPageTypes } = maintenance;
  const {
    rawPathFromUrl,
    navigateToHealthIssue,
    handleOpenSynthesisPending,
    handleOpenDuplicateReview,
    handleWikiTabChange,
  } = tabs;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconDatabase className="w-5 h-5" />
          {t('stats.title')}
        </CardTitle>
        <CardDescription>{t('stats.description')}</CardDescription>
      </CardHeader>
      <CardContent>
        {!stats && !isLoadingStats && (
          <Button onClick={loadStats} variant="outline" data-testid="wiki-load-stats-btn">
            {t('actions.loadStats')}
          </Button>
        )}

        {isLoadingStats && (
          <div className="text-center py-4 text-muted-foreground" data-testid="wiki-stats-loading">
            {t('loading')}
          </div>
        )}

        {stats && (
          <div className="space-y-4" data-testid="wiki-stats-panel">
            <WikiStatsBadges
              stats={stats}
              healthReport={healthReport}
              isLoadingHealthReport={isLoadingHealthReport}
              healthReportLoadError={healthReportLoadError}
              synthesisPendingCount={synthesisPendingCount}
              duplicateGroupsPending={duplicateGroupsPending}
              dedupBlocksCompile={dedupBlocksCompile}
              onOpenSynthesisPending={handleOpenSynthesisPending}
              onOpenDuplicateReview={handleOpenDuplicateReview}
            />
            <WikiHealthIssuesSection
              report={healthReport}
              isLoading={isLoadingHealthReport || (healthReport === null && !healthReportLoadError)}
              loadError={healthReportLoadError}
              expanded={healthReportExpanded}
              onToggleExpanded={() => setHealthReportExpanded((value) => !value)}
              onRecompile={() => void handleCompile()}
              isRecompiling={isCompiling}
              onRepair={() => void handleRepairPageTypes()}
              isRepairing={isRepairingTypes}
              onNavigateIssue={navigateToHealthIssue}
              onOpenDuplicateReview={handleOpenDuplicateReview}
              onOpenPendingEdits={() => handleWikiTabChange('pendingEdits')}
              onRefresh={() => void loadHealthReport()}
            />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
                <div className="text-xs text-muted-foreground">{t('stats.cognitiveIndex')}</div>
                <div
                  className={
                    stats.cognitive_index_ready
                      ? 'mt-1 text-sm font-medium text-emerald-600 dark:text-emerald-400'
                      : 'mt-1 text-sm font-medium text-amber-700 dark:text-amber-400'
                  }
                >
                  {stats.cognitive_index_ready ? t('stats.cognitiveReady') : t('stats.cognitivePending')}
                </div>
              </div>
              <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
                <div className="text-xs text-muted-foreground">{t('stats.cognitiveLog')}</div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {t('stats.cognitiveLogEntries', { count: stats.cognitive_log_entries ?? 0 })}
                </div>
              </div>
              <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
                <div className="text-xs text-muted-foreground">{t('stats.cognitiveHot')}</div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {stats.cognitive_hot_updated_at
                    ? t('stats.cognitiveHotUpdated', {
                        time: formatCognitiveUpdatedAt(stats.cognitive_hot_updated_at, locale),
                      })
                    : t('stats.cognitiveHotEmpty')}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-3xl font-bold">{stats.total_concepts}</div>
                <div className="text-sm text-muted-foreground">{t('stats.concepts')}</div>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-3xl font-bold">{stats.total_articles}</div>
                <div className="text-sm text-muted-foreground">{t('stats.articles')}</div>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-3xl font-bold">{stats.total_raw_files}</div>
                <div className="text-sm text-muted-foreground">{t('stats.rawFiles')}</div>
              </div>
              <div className="col-span-2 md:col-span-1 flex items-center justify-center">
                <Button onClick={loadStats} variant="ghost" size="sm">
                  {t('actions.refresh')}
                </Button>
              </div>
            </div>
            <div className="space-y-2 border-t border-border/60 pt-4">
              <div className="text-sm font-medium">{t('concepts.rawSourcesTitle')}</div>
              <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-muted-foreground/40" />
                  {t('concepts.rawIngestNotCompiled')}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 dark:bg-emerald-400" />
                  {t('concepts.rawIngestClean')}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-amber-500 dark:bg-amber-400" />
                  {t('concepts.rawIngestModified')}
                </span>
              </div>
              <WikiRawSourceTree
                treeData={rawTreeData}
                isLoading={isLoadingRawTree}
                agentScopeId={agentScopeId}
                highlightPath={rawPathFromUrl}
                onRawDeleted={() => void refreshIngestTreesSilently()}
              />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
