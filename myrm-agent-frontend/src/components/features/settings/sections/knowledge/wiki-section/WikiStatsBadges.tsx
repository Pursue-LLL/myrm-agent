'use client';

/**
 * [INPUT] ./types::WikiStats (POS: 知识库统计), ./wikiStatsFormat (POS: 时间与跳过原因的展示格式化), @/services/wikiService::WikiHealthReport (POS: 健康报告)
 * [OUTPUT] WikiStatsBadges: 统计面板顶部的状态徽标 (vault / 迁移 / 结构问题 / 资产索引 / 待综合 / 重复组 / 最近维护) 与三条提示 (上次维护摘要、资产视觉提示、结构问题尚未出报告)
 * [POS] 统计卡的上半部分; 待综合与重复组徽标是跳转到对应审核页的按钮, 重复组会拦下编译时用玫红色强调。
 */

import { useLocale, useTranslations } from 'next-intl';
import type { WikiHealthReport } from '@/services/wikiService';
import type { WikiStats } from './types';
import { formatCognitiveUpdatedAt, maintainSkippedBadgeLabel } from './wikiStatsFormat';

interface WikiStatsBadgesProps {
  stats: WikiStats;
  healthReport: WikiHealthReport | null;
  isLoadingHealthReport: boolean;
  healthReportLoadError: boolean;
  synthesisPendingCount: number;
  duplicateGroupsPending: number;
  dedupBlocksCompile: boolean;
  onOpenSynthesisPending: () => void;
  onOpenDuplicateReview: () => void;
}

export function WikiStatsBadges({
  stats,
  healthReport,
  isLoadingHealthReport,
  healthReportLoadError,
  synthesisPendingCount,
  duplicateGroupsPending,
  dedupBlocksCompile,
  onOpenSynthesisPending,
  onOpenDuplicateReview,
}: WikiStatsBadgesProps) {
  const t = useTranslations('settings.wiki');
  const locale = useLocale();

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span
          className={
            stats.vault_ready
              ? 'inline-flex items-center rounded-full bg-emerald-500/10 px-3 py-1 text-emerald-600 dark:text-emerald-400'
              : 'inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400'
          }
        >
          {stats.vault_ready ? t('stats.vaultReady') : t('stats.vaultNotReady')}
        </span>
        {stats.legacy_migrated ? (
          <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-3 py-1 text-emerald-600 dark:text-emerald-400">
            {t('stats.legacyMigrated')}
          </span>
        ) : (
          <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
            {t('stats.legacyPending')}
          </span>
        )}
        {(stats.structural_issues?.broken_links ?? 0) > 0 && (
          <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
            {t('stats.brokenLinks', { count: stats.structural_issues?.broken_links ?? 0 })}
          </span>
        )}
        {(stats.structural_issues?.invalid_frontmatter_types ?? 0) > 0 && (
          <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
            {t('stats.invalidPageTypes', {
              count: stats.structural_issues?.invalid_frontmatter_types ?? 0,
            })}
          </span>
        )}
        {(stats.structural_issues?.provenance_gaps ?? 0) > 0 && (
          <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
            {t('stats.provenanceGaps', {
              count: stats.structural_issues?.provenance_gaps ?? 0,
            })}
          </span>
        )}
        {(stats.asset_index?.total_files ?? 0) > 0 && (
          <span className="inline-flex items-center rounded-full bg-sky-500/10 px-3 py-1 text-sky-700 dark:text-sky-300">
            {t('stats.indexedAssets', { count: stats.asset_index?.indexed ?? 0 })}
          </span>
        )}
        {(stats.asset_index?.failed ?? 0) > 0 && (
          <span className="inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
            {t('stats.failedAssets', { count: stats.asset_index?.failed ?? 0 })}
          </span>
        )}
        {synthesisPendingCount > 0 && (
          <button
            type="button"
            onClick={onOpenSynthesisPending}
            className="inline-flex items-center rounded-full bg-violet-500/10 px-3 py-1 text-violet-700 transition-colors hover:bg-violet-500/20 dark:text-violet-300"
          >
            {t('stats.synthesisPending', { count: synthesisPendingCount })}
          </button>
        )}
        {duplicateGroupsPending > 0 && (
          <button
            type="button"
            onClick={onOpenDuplicateReview}
            className={
              dedupBlocksCompile
                ? 'inline-flex items-center rounded-full bg-rose-500/10 px-3 py-1 text-rose-700 transition-colors hover:bg-rose-500/20 dark:text-rose-300'
                : 'inline-flex items-center rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 transition-colors hover:bg-amber-500/20 dark:text-amber-300'
            }
          >
            {t('stats.duplicateGroupsPending', { count: duplicateGroupsPending })}
          </button>
        )}
        {stats.maintain_state?.last_run_at ? (
          <span className="inline-flex items-center rounded-full bg-muted px-3 py-1 text-muted-foreground">
            {stats.maintain_state.last_skipped_reason
              ? maintainSkippedBadgeLabel(stats.maintain_state.last_skipped_reason, t)
              : t('stats.lastMaintain', {
                  time: formatCognitiveUpdatedAt(stats.maintain_state.last_run_at, locale),
                })}
          </span>
        ) : (
          <span className="inline-flex items-center rounded-full bg-muted px-3 py-1 text-muted-foreground">
            {t('stats.lastMaintainNever')}
          </span>
        )}
      </div>
      {stats.maintain_state?.last_run_at &&
      !stats.maintain_state.last_skipped_reason &&
      (stats.maintain_state.last_issues_found > 0 || stats.maintain_state.last_issues_fixed > 0) ? (
        <p className="text-xs text-muted-foreground">
          {t('stats.lastMaintainSummary', {
            fixed: stats.maintain_state.last_issues_fixed,
            found: stats.maintain_state.last_issues_found,
          })}
        </p>
      ) : null}
      {(stats.asset_index?.total_files ?? 0) > 0 && !stats.asset_index?.enabled ? (
        <p className="text-xs text-amber-800/90 dark:text-amber-200/90">{t('stats.assetsVisionHint')}</p>
      ) : null}
      {(stats.structural_issues?.broken_links ?? 0) > 0 ||
      (stats.structural_issues?.invalid_frontmatter_types ?? 0) > 0 ||
      (stats.structural_issues?.provenance_gaps ?? 0) > 0 ? (
        !healthReport && !isLoadingHealthReport && !healthReportLoadError ? (
          <p className="text-xs text-amber-800/90 dark:text-amber-200/90">{t('stats.structuralHint')}</p>
        ) : null
      ) : null}
    </>
  );
}
