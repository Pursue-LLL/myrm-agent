'use client';

import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { motion } from 'framer-motion';
import {
  IconDatabase,
  IconBrain,
  IconChat,
  IconRefresh,
  IconAlertCircle,
  IconChart,
  IconArrowRight,
} from '@/components/features/icons/PremiumIcons';
import SettingsSection from '../SettingsSection';
import BudgetPolicySection from './BudgetPolicySection';
import ChannelBudgetSection from './ChannelBudgetSection';
import MemoryGuardianCard from '../knowledge/MemoryGuardianCard';
import AgentUsageCard from './AgentUsageCard';
import RoutingAnalyticsPanel, { formatTokenCount, formatCost } from './RoutingAnalyticsPanel';
import SessionAnalyticsDialog from './SessionAnalyticsDialog';
import { localizeReactNode } from '@/lib/utils/localeText';
import {
  getDailyUsage,
  getSessionUsage,
  getUsageStatistics,
  getGlobalActivityPatterns,
  getTopSessions,
  type DailyUsage,
  type SessionUsage,
  type UsageStats,
  type GlobalActivityPatterns,
  type TopSession,
} from '@/services/statistics';
import { IconClock, IconTarget } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import {
  StatCard,
  DailyChart,
  SessionTable,
  WeekDistributionChart,
  ActivityDailyChart,
  HourDistributionChart,
  ModelBreakdown,
  PrivacyRoutePanel,
} from './UsageStatisticsCharts';

function UsageStatisticsSection() {
  const t = useTranslations('settings.usageStatistics');
  const locale = useLocale();
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [daily, setDaily] = useState<DailyUsage[]>([]);
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [activity, setActivity] = useState<GlobalActivityPatterns | null>(null);
  const [topSessions, setTopSessions] = useState<TopSession[]>([]);
  const [topSessionMetric, setTopSessionMetric] = useState<'duration' | 'messages' | 'tokens' | 'tool_calls'>(
    'duration',
  );
  const [timeRange, setTimeRange] = useState<7 | 30 | 365>(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsData, dailyData, sessionData, activityData, topSessionsData] = await Promise.all([
        getUsageStatistics(),
        getDailyUsage(30),
        getSessionUsage(10),
        getGlobalActivityPatterns(timeRange),
        getTopSessions(topSessionMetric, 10, timeRange),
      ]);
      setStats(statsData);
      setDaily(dailyData.daily);
      setSessions(sessionData.sessions);
      setActivity(activityData);
      setTopSessions(topSessionsData);
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
            <IconAlertCircle className="text-destructive w-8 h-8" />
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

  if (!stats) return null;

  return localizeReactNode(
    <div className="space-y-6">
      <BudgetPolicySection />
      <ChannelBudgetSection />
      <MemoryGuardianCard />
      <SettingsSection
        title={t('title')}
        description={t('description')}
        action={
          <button
            onClick={fetchData}
            className="p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
            title={t('refresh')}
          >
            <IconRefresh className="w-4 h-4" />
          </button>
        }
      >
        {/* Overview cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            icon={IconChart}
            label={t('totalTokens')}
            value={formatTokenCount(stats.totalTokens)}
            colorClass="bg-primary/15 text-primary"
          />
          <StatCard
            icon={IconArrowRight}
            label={t('inputTokens')}
            value={formatTokenCount(stats.inputTokens)}
            colorClass="bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400"
          />
          <StatCard
            icon={() => <IconArrowRight className="w-4 h-4 rotate-90" />}
            label={t('outputTokens')}
            value={formatTokenCount(stats.outputTokens)}
            colorClass="bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-400"
          />
          <StatCard
            icon={IconChart}
            label={t('totalCost')}
            value={formatCost(stats.costUsd)}
            colorClass="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400"
          />
        </div>

        {/* Secondary stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
          <StatCard
            icon={IconDatabase}
            label={t('cacheHitRate')}
            value={`${(stats.cacheHitRate * 100).toFixed(1)}%`}
            subValue={formatTokenCount(stats.cachedTokens)}
            colorClass="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400"
          />
          <StatCard
            icon={IconDatabase}
            label={t('cacheSavings') || 'Cache Savings'}
            value={formatCost(stats.cacheSavingsUsd || 0)}
            colorClass="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400"
          />
          <StatCard
            icon={IconBrain}
            label={t('reasoningTokens')}
            value={formatTokenCount(stats.reasoningTokens)}
            colorClass="bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400"
          />
          <StatCard
            icon={IconChat}
            label={t('totalCalls')}
            value={stats.calls.toLocaleString()}
            colorClass="bg-sky-100 dark:bg-sky-900/40 text-sky-600 dark:text-sky-400"
          />
        </div>
      </SettingsSection>

      {/* Daily trend */}
      <SettingsSection title={t('trendsTitle')}>
        <DailyChart data={daily} t={t} />
      </SettingsSection>

      {/* Per-Agent Usage (auto-hidden when <=1 agent) */}
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
      <SettingsSection title={t('activityTitle')}>
        {activity && activity.active_days > 0 ? (
          <div className="space-y-6">
            {/* Time Range Selector */}
            <div className="flex items-center gap-2 pb-2 border-b border-border/50">
              <button
                onClick={() => setTimeRange(7)}
                className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors ${
                  timeRange === 7
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                7 Days / 7天
              </button>
              <button
                onClick={() => setTimeRange(30)}
                className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors ${
                  timeRange === 30
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                30 Days / 30天
              </button>
              <button
                onClick={() => setTimeRange(365)}
                className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors ${
                  timeRange === 365
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                All / 全部
              </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                icon={IconChart}
                label={t('activeDays')}
                value={activity.active_days.toString()}
                colorClass="bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400"
              />
              <StatCard
                icon={IconChart}
                label={t('maxStreak')}
                value={`${activity.max_streak} days`}
                colorClass="bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400"
              />
              <StatCard
                icon={IconChat}
                label={t('busiestDay')}
                value={['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][activity.busiest_day_of_week]}
                colorClass="bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-400"
              />
              <StatCard
                icon={IconChart}
                label={t('busiestHour')}
                value={`${activity.busiest_hour}:00`}
                colorClass="bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400"
              />
            </div>

            {/* Daily Trend Chart */}
            {activity.daily_activities && activity.daily_activities.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <IconChart className="w-4 h-4 text-primary" />
                  {t('dailyTrendActivity')}
                </div>
                <ActivityDailyChart data={activity.daily_activities} />
              </div>
            )}

            {/* Week Distribution Bar Chart */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <IconChart className="w-4 h-4 text-primary" />
                {t('weekDistribution')}
              </div>
              <WeekDistributionChart data={activity.by_day_of_week} />
            </div>

            {/* Hour Distribution Line Chart */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <IconChart className="w-4 h-4 text-primary" />
                {t('hourDistribution')}
              </div>
              <HourDistributionChart data={activity.by_hour} />
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground">
            <IconChart className="w-12 h-12 text-muted-foreground/30" />
            <div className="text-center">
              <p className="text-sm font-medium">{t('noActivityTitle')}</p>
              <p className="text-xs mt-1">{t('noActivityDesc')}</p>
            </div>
          </div>
        )}
      </SettingsSection>

      {/* Top Sessions (A3) */}
      <SettingsSection title={t('topSessionsTitle')}>
        {topSessions && topSessions.length > 0 ? (
          <div className="space-y-6">
            {/* Metric Selector */}
            <div className="flex items-center gap-2 pb-2 border-b border-border/50">
              {(['duration', 'messages', 'tokens', 'tool_calls'] as const).map((m) => {
                const metricLabels = {
                  duration: t('metricDuration'),
                  messages: t('metricMessages'),
                  tokens: t('metricTokens'),
                  tool_calls: t('metricToolCalls'),
                };
                const isActive = topSessionMetric === m;
                return (
                  <button
                    key={m}
                    onClick={() => setTopSessionMetric(m)}
                    className={cn(
                      'px-3 py-1.5 text-xs font-medium rounded-lg transition-all',
                      isActive
                        ? 'bg-primary/10 text-primary border border-primary/20'
                        : 'text-muted-foreground hover:bg-accent hover:text-foreground border border-transparent',
                    )}
                  >
                    {metricLabels[m]}
                  </button>
                );
              })}
            </div>

            {/* Top Sessions List */}
            <div className="space-y-3">
              {topSessions.map((session, idx) => {
                const duration = Math.floor(session.duration_ms / 60000);
                const metricDisplay = {
                  duration: `${duration}min`,
                  messages: `${session.message_count}`,
                  tokens: `${formatTokenCount(session.total_tokens)}`,
                  tool_calls: `${session.tool_calls}`,
                }[topSessionMetric];

                return (
                  <motion.div
                    key={session.session_id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className="flex items-center gap-4 p-4 rounded-xl bg-background/60 border border-border/40 hover:border-primary/40 hover:bg-background/80 transition-all"
                  >
                    {/* Rank Badge */}
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                      <span className="text-sm font-bold text-primary">#{idx + 1}</span>
                    </div>

                    {/* Session Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-muted-foreground truncate">
                          {session.session_id.substring(0, 12)}...
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(session.started_at * 1000).toLocaleDateString()}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <IconClock className="w-3.5 h-3.5" /> {duration}min
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <IconChat className="w-3.5 h-3.5" /> {session.message_count}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <IconTarget className="w-3.5 h-3.5" /> {session.tool_calls}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <IconChart className="w-3.5 h-3.5" /> {formatTokenCount(session.total_tokens)}
                        </span>
                      </div>
                    </div>

                    {/* Metric Value */}
                    <div className="flex-shrink-0 text-right">
                      <div className="text-2xl font-bold text-primary">{metricDisplay}</div>
                      <div className="text-xs text-muted-foreground capitalize">{topSessionMetric}</div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground">
            <IconChat className="w-12 h-12 text-muted-foreground/30" />
            <div className="text-center">
              <p className="text-sm font-medium">{t('noTopSessionsTitle')}</p>
              <p className="text-xs mt-1">{t('noTopSessionsDesc')}</p>
            </div>
          </div>
        )}
      </SettingsSection>

      {/* Session Analytics Dialog */}
      {selectedSessionId && (
        <SessionAnalyticsDialog sessionId={selectedSessionId} onClose={() => setSelectedSessionId(null)} />
      )}
    </div>,
    locale,
  );
}

export default UsageStatisticsSection;
