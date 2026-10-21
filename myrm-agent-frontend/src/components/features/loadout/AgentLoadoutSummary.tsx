'use client';

/**
 * [INPUT]
 * @/components/features/loadout/useAgentLoadoutSummary::useAgentLoadoutSummary (POS: Loadout data orchestration hook)
 * @/components/features/loadout/loadoutDeepLinks (POS: Settings deep-link SSOT)
 *
 * [OUTPUT]
 * AgentLoadoutSummary: Per-agent loadout summary panel with readiness badge and asset deep links.
 *
 * [POS]
 * Agent loadout summary UI. Surfaces shared contexts, skills, wiki, memory policy, and readiness
 * in a responsive tile grid with navigation into existing Settings sections.
 */

import { useEffect } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { ArrowRight, BookOpen, Brain, Loader2, ShieldCheck, Users, Wand2 } from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import {
  agentWikiHref,
  memoryExplorerHref,
  skillsSettingsHref,
  teamAssetsHubHref,
} from '@/components/features/loadout/loadoutDeepLinks';
import { readinessLevelTone, useAgentLoadoutSummary } from '@/components/features/loadout/useAgentLoadoutSummary';

interface AgentLoadoutSummaryProps {
  agentId: string | null;
  skillCount?: number;
  className?: string;
  compact?: boolean;
  refreshKey?: number;
  /** Override SC tile link — e.g. in-page `#shared-context-binding` on Capabilities tab. */
  sharedContextTileHref?: string;
}

function SummaryTile({ title, value, href, badge }: { title: string; value: string; href: string; badge?: number }) {
  return (
    <Link
      href={href}
      className="group flex flex-col gap-1 rounded-xl border border-border/50 bg-accent/20 p-4 transition-colors hover:border-primary/30 hover:bg-accent/40"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{title}</span>
        <div className="flex shrink-0 items-center gap-1.5">
          {badge !== undefined && badge > 0 && (
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
              {badge}
            </span>
          )}
          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </div>
      </div>
      <span className="text-sm font-medium text-foreground line-clamp-2">{value}</span>
    </Link>
  );
}

export function AgentLoadoutSummary({
  agentId,
  skillCount,
  className,
  compact = false,
  refreshKey = 0,
  sharedContextTileHref,
}: AgentLoadoutSummaryProps) {
  const t = useTranslations('loadout');
  const { data, loading, error } = useAgentLoadoutSummary({
    agentId,
    skillCount,
    enabled: Boolean(agentId),
    refreshKey,
  });

  useEffect(() => {
    if (typeof window === 'undefined' || loading || !data) {
      return;
    }
    if (window.location.hash.replace(/^#/, '') !== 'loadout') {
      return;
    }
    document.getElementById('loadout')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [loading, data]);

  if (!agentId) {
    return (
      <div
        className={cn(
          'rounded-xl border border-dashed border-border/60 bg-muted/20 px-4 py-3 text-sm text-muted-foreground',
          className,
        )}
      >
        {t('saveAgentFirst')}
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div
        className={cn(
          'flex items-center gap-2 rounded-xl border border-border/40 bg-accent/10 px-4 py-6 text-sm text-muted-foreground',
          className,
        )}
      >
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={cn(
          'rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive',
          className,
        )}
      >
        {error}
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const readinessLevel = data.readiness?.overall_level;
  const showReadinessBadge = data.readinessStatus === 'ok' && data.readiness != null && readinessLevel != null;
  const sharedLabel =
    data.bindingsStatus === 'unavailable'
      ? t('sharedContexts.unavailable')
      : data.boundContextNames.length > 0
        ? data.boundContextNames.slice(0, 2).join(', ') +
          (data.boundContextNames.length > 2 ? ` +${data.boundContextNames.length - 2}` : '')
        : t('sharedContexts.none');

  const proposalBadge =
    data.proposalsStatus === 'ok' && data.pendingProposalCount > 0 ? data.pendingProposalCount : undefined;

  const sharedContextHref = sharedContextTileHref ?? teamAssetsHubHref();

  const memoryLabel = data.memoryPolicy.enableMemory
    ? data.memoryPolicy.preCompactEnabled
      ? t('memoryPolicy.onWithPreCompact', { tokens: data.memoryPolicy.preCompactBudgetTokens })
      : t('memoryPolicy.on')
    : t('memoryPolicy.off');

  return (
    <section id="loadout" className={cn('space-y-4', className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
          {!compact && <p className="mt-1 text-xs text-muted-foreground">{t('subtitle')}</p>}
        </div>
        {showReadinessBadge && (
          <div
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
              readinessLevelTone(readinessLevel),
            )}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            {t(`readiness.${readinessLevel}`)}
          </div>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <SummaryTile
          title={t('tiles.sharedContexts')}
          value={sharedLabel}
          href={sharedContextHref}
          badge={proposalBadge}
        />
        <SummaryTile
          title={t('tiles.skills')}
          value={t('tiles.skillsCount', { count: data.skillCount })}
          href={skillsSettingsHref()}
        />
        <SummaryTile
          title={t('tiles.wiki')}
          value={data.wikiEnabled ? t('tiles.wikiOn') : t('tiles.wikiOff')}
          href={agentWikiHref(agentId)}
        />
        <SummaryTile title={t('tiles.memoryPolicy')} value={memoryLabel} href={memoryExplorerHref()} />
      </div>

      {data.readinessStatus === 'ok' && data.readiness && data.readiness.items.length > 0 && (
        <ul className="space-y-2 rounded-xl border border-border/40 bg-background/60 p-3 text-xs">
          {data.readiness.items.slice(0, compact ? 2 : 4).map((item) => (
            <li key={`${item.dimension}-${item.reason}`} className="flex flex-wrap items-start justify-between gap-2">
              <span className="text-muted-foreground">{item.reason}</span>
              <Link href={item.settings_path} className="font-medium text-primary hover:underline">
                {t('fix')}
              </Link>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline" size="sm" className="h-8 gap-1.5 text-xs">
          <Link href={teamAssetsHubHref()}>
            <Users className="h-3.5 w-3.5" />
            {t('openTeamAssets')}
          </Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="h-8 gap-1.5 text-xs">
          <Link href={agentWikiHref(agentId)}>
            <BookOpen className="h-3.5 w-3.5" />
            {t('openWiki')}
          </Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="h-8 gap-1.5 text-xs">
          <Link href={skillsSettingsHref()}>
            <Wand2 className="h-3.5 w-3.5" />
            {t('openSkills')}
          </Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="h-8 gap-1.5 text-xs">
          <Link href={memoryExplorerHref()}>
            <Brain className="h-3.5 w-3.5" />
            {t('openMemory')}
          </Link>
        </Button>
      </div>
    </section>
  );
}
