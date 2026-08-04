'use client';

/**
 * [INPUT]
 * @/components/features/memory/SharedContextPanel::SharedContextPanel (POS: Shared Context management UI)
 * @/components/features/loadout/loadoutDeepLinks (POS: Settings deep-link SSOT)
 *
 * [OUTPUT]
 * TeamAssetsHub: Team assets hub composing Shared Context panel with wiki/skills/memory entry cards.
 *
 * [POS]
 * Team assets hub UI. Aggregates team-level shared context management with quick links to wiki,
 * skills, and memory settings without duplicating their SSOT forms.
 */

import type { ReactNode } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { ArrowRight, BookOpen, Brain, Wand2 } from 'lucide-react';

import SharedContextPanel from '@/components/features/memory/SharedContextPanel';
import { memoryExplorerHref, skillsSettingsHref } from '@/components/features/loadout/loadoutDeepLinks';
import { cn } from '@/lib/utils/classnameUtils';

function AssetLinkCard({
  icon,
  title,
  description,
  href,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  href: string;
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
          <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </div>
        <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{description}</p>
      </div>
    </Link>
  );
}

export function TeamAssetsHub({ className }: { className?: string }) {
  const t = useTranslations('loadout.teamHub');

  return (
    <div className={cn('space-y-6', className)}>
      <div className="space-y-1">
        <h2 className="text-lg font-semibold text-foreground">{t('title')}</h2>
        <p className="text-sm text-muted-foreground">{t('subtitle')}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <AssetLinkCard
          icon={<BookOpen className="h-4 w-4" />}
          title={t('wikiTitle')}
          description={t('wikiDesc')}
          href="/settings/wiki"
        />
        <AssetLinkCard
          icon={<Wand2 className="h-4 w-4" />}
          title={t('skillsTitle')}
          description={t('skillsDesc')}
          href={skillsSettingsHref()}
        />
        <AssetLinkCard
          icon={<Brain className="h-4 w-4" />}
          title={t('memoryTitle')}
          description={t('memoryDesc')}
          href={memoryExplorerHref()}
        />
      </div>

      <SharedContextPanel />
    </div>
  );
}
