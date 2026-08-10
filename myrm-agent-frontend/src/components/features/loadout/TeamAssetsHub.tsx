'use client';

/**
 * [INPUT]
 * @/components/features/memory/SharedContextPanel::SharedContextPanel (POS: Shared Context management UI)
 * @/components/features/loadout/loadoutDeepLinks (POS: Settings deep-link SSOT)
 * @/components/features/loadout/useTeamAssetsHubSummary::useTeamAssetsHubSummary (POS: Team assets data orchestration hook)
 * @/components/features/loadout/useAgentLoadoutSummary::readinessLevelTone (POS: Readiness badge tone helper)
 *
 * [OUTPUT]
 * TeamAssetsHub: Team assets hub composing Shared Context panel with wiki/skills/memory entry cards,
 * a global asset status summary, and a cross-agent readiness overview.
 *
 * [POS]
 * Team assets hub UI. Aggregates team-level shared context management, live asset health counts,
 * and a one-screen readiness overview for every agent, with deep links into existing Settings
 * sections — without duplicating their SSOT forms or audit logic.
 */

import type { ReactNode } from 'react';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { ArrowRight, BookOpen, Brain, Loader2, ShieldAlert, Wand2 } from 'lucide-react';

import SharedContextPanel from '@/components/features/memory/SharedContextPanel';
import {
  agentSettingsHref,
  memoryExplorerHref,
  skillsSettingsHref,
} from '@/components/features/loadout/loadoutDeepLinks';
import { readinessLevelTone } from '@/components/features/loadout/useAgentLoadoutSummary';
import { useTeamAssetsHubSummary } from '@/components/features/loadout/useTeamAssetsHubSummary';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { cn } from '@/lib/utils/classnameUtils';

function AssetLinkCard({
  icon,
  title,
  description,
  href,
  badge,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  href: string;
  badge?: number;
}) {
  return (
    <Link
      href={href}
      className="group flex items-start gap-3 rounded-xl border border-border/50 bg-accent/20 p-4 transition-colors hover:border-primary/30 hover:bg-accent/40"
    >
      <div className="mt-0.5 text-primary/80">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          <div className="flex shrink-0 items-center gap-1.5">
            {badge !== undefined && badge > 0 && (
              <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
                {badge}
              </span>
            )}
            <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
          </div>
        </div>
        <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{description}</p>
      </div>
    </Link>
  );
}

function SummaryStat({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="rounded-xl border border-border/50 bg-accent/20 p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 text-lg font-semibold text-foreground', muted && 'text-muted-foreground')}>{value}</div>
    </div>
  );
}

export function TeamAssetsHub({ className }: { className?: string }) {
  const locale = useLocale();
  const t = useTranslations('loadout');
  const { summary, loading, error } = useTeamAssetsHubSummary();

  const blockedAgents = summary?.agents.filter((agent) => agent.readinessLevel === 'blocked') ?? [];

  return (
    <div className={cn('space-y-6', className)}>
      <div className="space-y-1">
        <h2 className="text-lg font-semibold text-foreground">{t('teamHub.title')}</h2>
        <p className="text-sm text-muted-foreground">{t('teamHub.subtitle')}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <AssetLinkCard
          icon={<BookOpen className="h-4 w-4" />}
          title={t('teamHub.wikiTitle')}
          description={t('teamHub.wikiDesc')}
          href="/settings/wiki"
        />
        <AssetLinkCard
          icon={<Wand2 className="h-4 w-4" />}
          title={t('teamHub.skillsTitle')}
          description={t('teamHub.skillsDesc')}
          href={skillsSettingsHref()}
          badge={summary?.skillStatus === 'ok' ? summary.skillCount : undefined}
        />
        <AssetLinkCard
          icon={<Brain className="h-4 w-4" />}
          title={t('teamHub.memoryTitle')}
          description={t('teamHub.memoryDesc')}
          href={memoryExplorerHref()}
          badge={summary?.pendingStatus === 'ok' ? summary.pendingCount : undefined}
        />
      </div>

      {loading && !summary ? (
        <div className="flex items-center gap-2 rounded-xl border border-border/40 bg-accent/10 px-4 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('teamHub.summaryLoading')}
        </div>
      ) : error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : summary ? (
        <section className="space-y-3 rounded-xl border border-border/40 bg-background/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">{t('teamHub.overviewTitle')}</h3>
            {blockedAgents.length > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-destructive/40 bg-destructive/5 px-2.5 py-1 text-xs font-medium text-destructive">
                <ShieldAlert className="h-3.5 w-3.5" />
                {t('teamHub.blockedCount', { count: blockedAgents.length })}
              </span>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <SummaryStat
              label={t('teamHub.memoryStat')}
              value={summary.enableMemory ? t('teamHub.memoryOn') : t('teamHub.memoryOff')}
            />
            <SummaryStat
              label={t('teamHub.skillsStat')}
              value={summary.skillStatus === 'unavailable' ? t('teamHub.unavailable') : String(summary.skillCount)}
              muted={summary.skillStatus === 'unavailable'}
            />
            <SummaryStat
              label={t('teamHub.pendingStat')}
              value={summary.pendingStatus === 'unavailable' ? t('teamHub.unavailable') : String(summary.pendingCount)}
              muted={summary.pendingStatus === 'unavailable'}
            />
          </div>

          {summary.agentsStatus === 'ok' && summary.agents.length > 0 && (
            <div className="space-y-2">
              {summary.agents.map((agent) => (
                <Link
                  key={agent.agentId}
                  href={agentSettingsHref(agent.agentId)}
                  className="flex items-center gap-3 rounded-lg border border-border/50 bg-accent/20 px-3 py-2.5 transition-colors hover:border-primary/30 hover:bg-accent/40"
                >
                  <span
                    className={cn(
                      'inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium',
                      agent.readinessStatus === 'ok' && agent.readinessLevel
                        ? readinessLevelTone(agent.readinessLevel)
                        : 'text-muted-foreground border-border/60',
                    )}
                  >
                    {agent.readinessStatus === 'ok' && agent.readinessLevel
                      ? t(`readiness.${agent.readinessLevel}`)
                      : t('teamHub.unavailable')}
                  </span>
                  {agent.isBuiltIn && (
                    <span className="shrink-0 rounded-full border border-border/60 bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                      {t('teamHub.builtIn')}
                    </span>
                  )}
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
                    {getBuiltinAgentName(agent.agentId, agent.name, locale)}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {t('teamHub.agentSummary', {
                      skills: agent.skillCount,
                      wiki: agent.wikiEnabled ? t('teamHub.wikiOn') : t('teamHub.wikiOff'),
                      cron: agent.cronCount,
                    })}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </section>
      ) : null}

      <SharedContextPanel />
    </div>
  );
}
