/**
 * [INPUT] SkillGrowthCaseSummary via @/services/skill/growth; useGrowthTypeLabel
 * [OUTPUT] GrowthCaseTitleRow: 成长提案卡片的标题与状态/来源/验证/安全徽章行
 * [POS] features/skills/growth-card 卡片头部；只展示，不持有状态
 */
'use client';

import { useTranslations } from 'next-intl';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { useGrowthTypeLabel } from '@/components/features/growth/useGrowthTypeLabel';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

const SCAN_TRUST_LEVELS: readonly string[] = ['trusted', 'installed', 'untrusted', 'reject'];

function isScanTrustLevel(value: string): boolean {
  return SCAN_TRUST_LEVELS.includes(value);
}

const STATUS_STYLES: Record<
  SkillGrowthCaseSummary['status'],
  { badge: string; tone: 'default' | 'secondary' | 'destructive' | 'outline' }
> = {
  PENDING_REVIEW: {
    badge: 'border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-300',
    tone: 'outline',
  },
  AUTO_APPLIED: {
    badge: 'border-emerald-300 text-emerald-700 dark:border-emerald-700 dark:text-emerald-300',
    tone: 'outline',
  },
  FAILED_SCAN: { badge: 'border-red-300 text-red-700 dark:border-red-700 dark:text-red-300', tone: 'outline' },
  BLOCKED_LOCKED: {
    badge: 'border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-300',
    tone: 'outline',
  },
  APPROVED: { badge: 'border-sky-300 text-sky-700 dark:border-sky-700 dark:text-sky-300', tone: 'outline' },
  REJECTED: { badge: 'border-rose-300 text-rose-700 dark:border-rose-700 dark:text-rose-300', tone: 'outline' },
  APPLY_FAILED: {
    badge: 'border-orange-300 text-orange-700 dark:border-orange-700 dark:text-orange-300',
    tone: 'outline',
  },
};

function scanTrustStyle(level: string): string {
  switch (level) {
    case 'trusted':
      return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:border-emerald-500/50 dark:text-emerald-300';
    case 'installed':
      return 'border-sky-500/40 bg-sky-500/10 text-sky-700 dark:border-sky-500/50 dark:text-sky-300';
    case 'untrusted':
      return 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:border-amber-500/50 dark:text-amber-300';
    default:
      return 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:border-rose-500/50 dark:text-rose-300';
  }
}

interface GrowthCaseTitleRowProps {
  item: SkillGrowthCaseSummary;
  isSimple: boolean;
}

export function GrowthCaseTitleRow({ item, isSimple }: GrowthCaseTitleRowProps) {
  const t = useTranslations('settings.skills.growth');
  const growthTypeLabel = useGrowthTypeLabel();
  const statusStyle = STATUS_STYLES[item.status];
  const statusLabel = t(`status.${item.status}` as Parameters<typeof t>[0]);
  const sourceLabel =
    item.source === 'evolution'
      ? t('source.manualEvolution')
      : item.growthType === 'semantic_memory'
        ? t('source.memoryExtraction')
        : t('source.backgroundReview');
  const scan = item.securityScanSummary;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <h3 className="truncate text-base font-semibold text-foreground">{item.skillName}</h3>
      <Badge variant={statusStyle.tone} className={cn('text-[11px]', statusStyle.badge)}>
        {statusLabel}
      </Badge>
      <Badge variant="secondary" className="text-[11px]">
        {sourceLabel}
      </Badge>
      {item.growthType !== 'semantic_memory' && (
        <Badge variant="outline" className="text-[11px]">
          {growthTypeLabel(item.growthType)}
        </Badge>
      )}
      {item.impactedDependents.length > 0 && (
        <Badge
          variant="outline"
          className="text-[11px] border-amber-400/70 text-amber-700 dark:border-amber-700 dark:text-amber-300"
          title={t('impactedDependents.tooltip', { count: item.impactedDependents.length })}
        >
          {t('impactedDependents.label', { count: item.impactedDependents.length })}
        </Badge>
      )}
      {item.verificationProof?.is_verified && (
        <Badge
          variant="outline"
          className="text-[11px] border-emerald-500/70 bg-emerald-50/50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-300 inline-flex items-center gap-1"
        >
          <ShieldCheck className="h-3 w-3" />
          {t('verifiedBadge')}
        </Badge>
      )}
      {!isSimple && item.targetLayer && (
        <Badge
          variant="outline"
          className="text-[11px] font-mono bg-indigo-50/50 text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800"
        >
          {t('targetLayer', { layer: item.targetLayer })}
        </Badge>
      )}
      {!isSimple && item.targetPathology && (
        <Badge
          variant="outline"
          className="text-[11px] font-mono bg-purple-50/50 text-purple-700 dark:bg-purple-950/30 dark:text-purple-300 border-purple-200 dark:border-purple-800"
        >
          {t('targetPathology', { pathology: item.targetPathology })}
        </Badge>
      )}
      {item.verificationProof?.hollow_detected && (
        <Badge
          variant="outline"
          className="text-[11px] border-rose-500/70 bg-rose-50/50 text-rose-700 dark:border-rose-700 dark:bg-rose-950/20 dark:text-rose-300 inline-flex items-center gap-1"
        >
          <ShieldAlert className="h-3 w-3" />
          {t('hollowBlockedBadge')}
        </Badge>
      )}
      {scan && (
        <Badge
          variant="outline"
          className={cn(
            'text-[11px] inline-flex items-center gap-1 font-medium',
            scanTrustStyle(scan.trust_recommendation),
          )}
          title={t('securityScan.badgeTitle', { score: scan.score })}
        >
          {scan.score >= 50 ? <ShieldCheck className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
          <span>
            {scan.score}/100
            {isScanTrustLevel(scan.trust_recommendation) &&
              ` · ${t(`securityScan.risk.${scan.trust_recommendation}` as Parameters<typeof t>[0])}`}
          </span>
        </Badge>
      )}
    </div>
  );
}
