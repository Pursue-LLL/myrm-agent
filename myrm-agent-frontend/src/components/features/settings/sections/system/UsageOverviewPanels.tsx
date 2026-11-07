'use client';

/**
 * [INPUT] @/services/statistics::UsageStats, PromptCacheRadarData (POS: 用量统计 DTO), @/services/wiki/evidenceMetrics::WikiEvidenceSummary (POS: Wiki 证据汇总 DTO), ./UsageStatisticsCharts::StatCard
 * [OUTPUT] UsageOverviewCards: 总览与次级统计卡及全局 Prompt Cache 雷达; UsageWikiEvidenceSection: Wiki 证据治理卡片组
 * [POS] UsageStatisticsSection 的总览区块，纯展示，数据与刷新由父级持有。
 */

import { useTranslations } from 'next-intl';
import SettingsSection from '../SettingsSection';
import {
  IconDatabase,
  IconBrain,
  IconChat,
  IconAlertCircle,
  IconChart,
  IconArrowRight,
  IconExplore,
  IconClock,
  IconTarget,
} from '@/components/features/icons/PremiumIcons';
import { formatTokenCount, formatCost } from './RoutingAnalyticsPanel';
import { type UsageStats, type PromptCacheRadarData } from '@/services/statistics';
import { type WikiEvidenceSummary } from '@/services/wiki/evidenceMetrics';
import { StatCard } from './UsageStatisticsCharts';

interface UsageOverviewCardsProps {
  stats: UsageStats;
  promptCacheRadar: PromptCacheRadarData | null;
}

export function UsageOverviewCards({ stats, promptCacheRadar }: UsageOverviewCardsProps) {
  const t = useTranslations('settings.usageStatistics');

  return (
    <>
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
          label={t('cacheSavings')}
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

      {/* Global Prompt Cache Radar */}
      {promptCacheRadar && promptCacheRadar.sessions_tracked > 0 && (
        <div className="rounded-xl border border-border/50 bg-linear-to-r from-emerald-500/5 via-teal-500/5 to-primary/5 p-4 mt-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2">
              <IconDatabase className="w-4 h-4 text-emerald-500" />
              <span className="font-semibold text-sm text-foreground">{t('cacheRadarTitle')}</span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-medium">
                {t('cacheRadarWindow', {
                  days: promptCacheRadar.days,
                  sessions: promptCacheRadar.sessions_tracked,
                })}
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              {t('cacheRadarSavings')}{' '}
              <span className="font-mono font-semibold text-emerald-600 dark:text-emerald-400 text-sm">
                ${promptCacheRadar.estimated_savings_usd.toFixed(4)}
              </span>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className="bg-background/80 rounded-lg p-2 border border-border/40">
              <div className="text-muted-foreground text-[11px]">{t('cacheHitRate')}</div>
              <div className="text-base font-bold text-foreground font-mono mt-0.5">
                {(promptCacheRadar.prompt_cache_hit_ratio * 100).toFixed(1)}%
              </div>
            </div>
            <div className="bg-background/80 rounded-lg p-2 border border-border/40">
              <div className="text-muted-foreground text-[11px]">{t('cacheRadarCachedTokens')}</div>
              <div className="text-base font-bold text-emerald-600 dark:text-emerald-400 font-mono mt-0.5">
                {formatTokenCount(promptCacheRadar.total_cache_read_tokens)}
              </div>
            </div>
            <div className="bg-background/80 rounded-lg p-2 border border-border/40">
              <div className="text-muted-foreground text-[11px]">{t('cacheRadarFreshInput')}</div>
              <div className="text-base font-bold text-foreground font-mono mt-0.5">
                {formatTokenCount(promptCacheRadar.fresh_input_tokens)}
              </div>
            </div>
            <div className="bg-background/80 rounded-lg p-2 border border-border/40">
              <div className="text-muted-foreground text-[11px]">{t('cacheRadarTotalPrompt')}</div>
              <div className="text-base font-bold text-foreground font-mono mt-0.5">
                {formatTokenCount(promptCacheRadar.total_prompt_tokens)}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function UsageWikiEvidenceSection({ wikiEvidence }: { wikiEvidence: WikiEvidenceSummary }) {
  const t = useTranslations('settings.usageStatistics');

  return (
    <SettingsSection title={t('wikiEvidenceTitle')} description={t('wikiEvidenceDescription')}>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <StatCard
          icon={IconTarget}
          label={t('wikiDeepVerificationRate')}
          value={`${(wikiEvidence.deep_verification_rate * 100).toFixed(1)}%`}
          subValue={wikiEvidence.deep_verification_count.toLocaleString()}
          colorClass="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400"
        />
        <StatCard
          icon={IconExplore}
          label={t('wikiSnippetExpansionRate')}
          value={`${(wikiEvidence.snippet_expansion_rate * 100).toFixed(1)}%`}
          subValue={wikiEvidence.snippet_open_count.toLocaleString()}
          colorClass="bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400"
        />
        <StatCard
          icon={IconArrowRight}
          label={t('wikiRequeryRate')}
          value={`${(wikiEvidence.requery_rate * 100).toFixed(1)}%`}
          subValue={wikiEvidence.requery_count.toLocaleString()}
          colorClass="bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-400"
        />
        <StatCard
          icon={IconAlertCircle}
          label={t('wikiNegativeOutcomeRate')}
          value={`${(wikiEvidence.quality_outcome_negative_rate * 100).toFixed(1)}%`}
          subValue={wikiEvidence.quality_outcome_negative_count.toLocaleString()}
          colorClass={
            wikiEvidence.quality_outcome_negative_count > 0
              ? 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400'
              : 'bg-muted text-muted-foreground'
          }
        />
        <StatCard
          icon={IconClock}
          label={t('wikiVerificationDwell')}
          value={`${Math.round((wikiEvidence.verification_dwell_avg_ms || 0) / 1000)}s`}
          subValue={wikiEvidence.verification_dwell_sample_count.toLocaleString()}
          colorClass="bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400"
        />
        <StatCard
          icon={IconAlertCircle}
          label={t('wikiTelemetryDrops')}
          value={wikiEvidence.dropped_event_count.toLocaleString()}
          colorClass={
            wikiEvidence.dropped_event_count > 0
              ? 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400'
              : 'bg-muted text-muted-foreground'
          }
        />
      </div>
      <div className="mt-3 text-xs text-muted-foreground">
        {t('wikiEvidenceWindow', { days: wikiEvidence.days, retentionDays: wikiEvidence.retention_days })}
      </div>
    </SettingsSection>
  );
}
