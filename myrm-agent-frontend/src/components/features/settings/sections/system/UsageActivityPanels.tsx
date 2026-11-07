'use client';

/**
 * [INPUT] @/services/statistics::GlobalActivityPatterns, TopSession (POS: 活跃度与 Top 会话 DTO), ./UsageStatisticsCharts (POS: 分布图表)
 * [OUTPUT] UsageActivitySection: 活跃度统计与时间范围切换; UsageTopSessionsSection: Top 会话榜与指标切换; UsageTimeRange / TopSessionMetric: 两个切换器的取值类型
 * [POS] UsageStatisticsSection 的活跃度区块，选中的时间范围与指标由父级持有并驱动重新加载。
 */

import { useLocale, useTranslations } from 'next-intl';
import { motion } from 'framer-motion';
import SettingsSection from '../SettingsSection';
import { IconChat, IconChart, IconClock, IconTarget } from '@/components/features/icons/PremiumIcons';
import { formatTokenCount } from './RoutingAnalyticsPanel';
import { weekdayLabels } from '@/lib/utils/weekdayLabels';
import { type GlobalActivityPatterns, type TopSession } from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';
import { StatCard, WeekDistributionChart, ActivityDailyChart, HourDistributionChart } from './UsageStatisticsCharts';

const TIME_RANGES = [
  { days: 7, labelKey: 'timeRange7Days' },
  { days: 30, labelKey: 'timeRange30Days' },
  { days: 365, labelKey: 'timeRangeAll' },
] as const;

const TOP_SESSION_METRICS = ['duration', 'messages', 'tokens', 'tool_calls'] as const;

export type UsageTimeRange = (typeof TIME_RANGES)[number]['days'];
export type TopSessionMetric = (typeof TOP_SESSION_METRICS)[number];

interface UsageActivitySectionProps {
  activity: GlobalActivityPatterns | null;
  timeRange: UsageTimeRange;
  onTimeRangeChange: (range: UsageTimeRange) => void;
}

interface UsageTopSessionsSectionProps {
  topSessions: TopSession[];
  metric: TopSessionMetric;
  onMetricChange: (metric: TopSessionMetric) => void;
}

export function UsageActivitySection({ activity, timeRange, onTimeRangeChange }: UsageActivitySectionProps) {
  const t = useTranslations('settings.usageStatistics');
  const locale = useLocale();

  return (
    <SettingsSection title={t('activityTitle')}>
      {activity && activity.active_days > 0 ? (
        <div className="space-y-6">
          {/* Time Range Selector */}
          <div className="flex items-center gap-2 pb-2 border-b border-border/50">
            {TIME_RANGES.map(({ days, labelKey }) => (
              <button
                key={days}
                onClick={() => onTimeRangeChange(days)}
                className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors ${
                  timeRange === days
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                {t(labelKey)}
              </button>
            ))}
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
              value={t('daysCount', { count: activity.max_streak })}
              colorClass="bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400"
            />
            <StatCard
              icon={IconChat}
              label={t('busiestDay')}
              value={weekdayLabels(locale)[activity.busiest_day_of_week] || '-'}
              colorClass="bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-400"
            />
            <StatCard
              icon={IconChart}
              label={t('busiestHour')}
              value={`${activity.busiest_hour}:00 (${activity.timezone || 'UTC'})`}
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
            <WeekDistributionChart data={activity.by_day_of_week} locale={locale} />
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
  );
}

export function UsageTopSessionsSection({ topSessions, metric, onMetricChange }: UsageTopSessionsSectionProps) {
  const t = useTranslations('settings.usageStatistics');

  return (
    <SettingsSection title={t('topSessionsTitle')}>
      {topSessions && topSessions.length > 0 ? (
        <div className="space-y-6">
          {/* Metric Selector */}
          <div className="flex items-center gap-2 pb-2 border-b border-border/50">
            {TOP_SESSION_METRICS.map((m) => {
              const metricLabels = {
                duration: t('metricDuration'),
                messages: t('metricMessages'),
                tokens: t('metricTokens'),
                tool_calls: t('metricToolCalls'),
              };
              const isActive = metric === m;
              return (
                <button
                  key={m}
                  onClick={() => onMetricChange(m)}
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
              }[metric];

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
                    <div className="text-xs text-muted-foreground capitalize">{metric}</div>
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
  );
}
