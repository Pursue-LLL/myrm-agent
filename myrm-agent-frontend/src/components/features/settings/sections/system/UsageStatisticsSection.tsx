'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconRefresh, IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import SettingsSection from '../SettingsSection';
import BudgetPolicySection from './BudgetPolicySection';
import ChannelBudgetSection from './ChannelBudgetSection';
import AgentCommerceBudgetSection from './AgentCommerceBudgetSection';
import MemoryGuardianCard from '../knowledge/MemoryGuardianCard';
import AgentUsageCard from './AgentUsageCard';
import RoutingAnalyticsPanel from './RoutingAnalyticsPanel';
import SessionAnalyticsDialog from './SessionAnalyticsDialog';
import { Download } from 'lucide-react';
import { downloadUsageCsv } from './usageExport';
import {
  getDailyUsage,
  getSessionUsage,
  getUsageStatistics,
  getGlobalActivityPatterns,
  getTopSessions,
  getPromptCacheRadar,
  type DailyUsage,
  type SessionUsage,
  type UsageStats,
  type GlobalActivityPatterns,
  type TopSession,
  type PromptCacheRadarData,
} from '@/services/statistics';
import { getWikiEvidenceSummary, type WikiEvidenceSummary } from '@/services/wiki/evidenceMetrics';
import { DailyChart, SessionTable, ModelBreakdown, PrivacyRoutePanel } from './UsageStatisticsCharts';
import { UsageOverviewCards, UsageWikiEvidenceSection } from './UsageOverviewPanels';
import {
  UsageActivitySection,
  UsageTopSessionsSection,
  type TopSessionMetric,
  type UsageTimeRange,
} from './UsageActivityPanels';

function UsageStatisticsSection() {
  const t = useTranslations('settings.usageStatistics');
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [daily, setDaily] = useState<DailyUsage[]>([]);
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [activity, setActivity] = useState<GlobalActivityPatterns | null>(null);
  const [topSessions, setTopSessions] = useState<TopSession[]>([]);
  const [wikiEvidence, setWikiEvidence] = useState<WikiEvidenceSummary | null>(null);
  const [promptCacheRadar, setPromptCacheRadar] = useState<PromptCacheRadarData | null>(null);
  const [topSessionMetric, setTopSessionMetric] = useState<TopSessionMetric>('duration');
  const [timeRange, setTimeRange] = useState<UsageTimeRange>(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsData, dailyData, sessionData, activityData, topSessionsData, wikiEvidenceData, cacheRadarData] =
        await Promise.all([
          getUsageStatistics(),
          getDailyUsage(30),
          getSessionUsage(10),
          getGlobalActivityPatterns(timeRange),
          getTopSessions(topSessionMetric, 10, timeRange),
          getWikiEvidenceSummary(timeRange).catch((error) => {
            console.warn('[UsageStatistics] Failed to load wiki evidence summary:', error);
            return null;
          }),
          getPromptCacheRadar(timeRange).catch((error) => {
            console.warn('[UsageStatistics] Failed to load prompt cache radar:', error);
            return null;
          }),
        ]);
      setStats(statsData);
      setDaily(dailyData.daily);
      setSessions(sessionData.sessions);
      setActivity(activityData);
      setTopSessions(topSessionsData);
      setWikiEvidence(wikiEvidenceData);
      setPromptCacheRadar(cacheRadarData);
    } catch (e) {
      console.error('[UsageStatistics] Failed to load data:', e);
      setError(e instanceof Error ? e.message : 'Failed to load statistics');
    } finally {
      setLoading(false);
    }
  }, [timeRange, topSessionMetric]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="space-y-6">
        <SettingsSection title={t('title')} description={t('description')}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-background/60 animate-pulse" />
            ))}
          </div>
          <div className="h-40 rounded-xl bg-background/60 animate-pulse" />
        </SettingsSection>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <SettingsSection title={t('title')} description={t('description')}>
          <div className="flex flex-col items-center gap-3 py-8 text-muted-foreground">
            <IconAlertCircle className="text-destructive-text w-8 h-8" />
            <span className="text-sm text-center">{error}</span>
            <button onClick={fetchData} className="flex items-center gap-1.5 text-xs text-primary hover:underline">
              <IconRefresh className="w-3 h-3" />
              {t('retry')}
            </button>
          </div>
        </SettingsSection>
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  return (
    <div className="space-y-6">
      <BudgetPolicySection />
      <ChannelBudgetSection />
      <AgentCommerceBudgetSection />
      <MemoryGuardianCard />
      <SettingsSection
        title={t('title')}
        description={t('description')}
        action={
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              data-testid="export-usage-csv-btn"
              onClick={() => downloadUsageCsv(stats, daily)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border border-border/60 hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
              title={t('exportCsvTitle')}
            >
              <Download className="w-3.5 h-3.5" />
              <span>{t('exportCsv')}</span>
            </button>
            <button
              onClick={fetchData}
              className="p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
              title={t('refresh')}
            >
              <IconRefresh className="w-4 h-4" />
            </button>
          </div>
        }
      >
        <UsageOverviewCards stats={stats} promptCacheRadar={promptCacheRadar} />
      </SettingsSection>

      {wikiEvidence && <UsageWikiEvidenceSection wikiEvidence={wikiEvidence} />}

      {/* Daily trend */}
      <SettingsSection title={t('trendsTitle')}>
        <DailyChart data={daily} t={t} />
      </SettingsSection>

      {/* Per-Agent Usage (hidden until an agent has recorded usage) */}
      <AgentUsageCard />

      {/* Routing analytics (conditional) */}
      {stats.routingBreakdown && Object.keys(stats.routingBreakdown).length > 0 && (
        <SettingsSection title={t('routingTitle')}>
          <RoutingAnalyticsPanel stats={stats} t={t} />
        </SettingsSection>
      )}

      {/* Privacy route analytics (conditional) */}
      {stats.privacyRouteBreakdown && Object.keys(stats.privacyRouteBreakdown).length > 0 && (
        <SettingsSection title={t('privacyRoutingTitle')}>
          <PrivacyRoutePanel breakdown={stats.privacyRouteBreakdown} t={t} />
        </SettingsSection>
      )}

      {/* Model breakdown + Sessions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SettingsSection title={t('modelsTitle')}>
          <ModelBreakdown stats={stats} t={t} timeRange={timeRange} onSelectSession={setSelectedSessionId} />
        </SettingsSection>

        <SettingsSection title={t('sessionsTitle')}>
          <SessionTable sessions={sessions} t={t} onSelectSession={setSelectedSessionId} />
        </SettingsSection>
      </div>

      {/* Global Activity Patterns */}
      <UsageActivitySection activity={activity} timeRange={timeRange} onTimeRangeChange={setTimeRange} />

      {/* Top Sessions (A3) */}
      <UsageTopSessionsSection
        topSessions={topSessions}
        metric={topSessionMetric}
        onMetricChange={setTopSessionMetric}
      />

      {/* Session Analytics Dialog */}
      {selectedSessionId && (
        <SessionAnalyticsDialog sessionId={selectedSessionId} onClose={() => setSelectedSessionId(null)} />
      )}
    </div>
  );
}

export default UsageStatisticsSection;
