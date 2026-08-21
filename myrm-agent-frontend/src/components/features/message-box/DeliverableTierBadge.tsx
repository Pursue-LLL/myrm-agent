'use client';

/**
 * [INPUT]
 * @/store/chat/types::Message['deliverableTier']
 *
 * [OUTPUT]
 * DeliverableTierBadge: Micro-interaction badge indicating deliverable confidence tier
 * (VERIFIED | ARTIFACT | RESEARCH | PLAN) with interactive evidence HoverCard.
 *
 * [POS]
 * Rendered in MessageBox header to give users instant, verifiable confidence regarding agent output.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/primitives/hover-card';
import { Badge } from '@/components/primitives/badge';
import { IconCheck, IconFolder, IconExplore, IconAsk } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';

export interface DeliverableTierData {
  tier: 'VERIFIED' | 'ARTIFACT' | 'RESEARCH' | 'PLAN';
  evidence?: {
    verification_count?: number;
    verification_categories?: string[];
    files_written?: string[];
    sources_count?: number;
    gatekeeper_passed?: boolean;
    details?: string;
  };
}

interface DeliverableTierBadgeProps {
  data: DeliverableTierData;
  className?: string;
}

export function DeliverableTierBadge({ data, className }: DeliverableTierBadgeProps) {
  const t = useTranslations('chat.deliverableTier');
  const { tier, evidence } = data;

  const config = {
    VERIFIED: {
      label: t('verified'),
      desc: t('verifiedDesc'),
      icon: IconCheck,
      badgeClass:
        'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800/60',
      dotClass: 'bg-emerald-500',
    },
    ARTIFACT: {
      label: t('artifact'),
      desc: t('artifactDesc'),
      icon: IconFolder,
      badgeClass:
        'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800/60',
      dotClass: 'bg-blue-500',
    },
    RESEARCH: {
      label: t('research'),
      desc: t('researchDesc'),
      icon: IconExplore,
      badgeClass:
        'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/40 dark:text-purple-400 dark:border-purple-800/60',
      dotClass: 'bg-purple-500',
    },
    PLAN: {
      label: t('plan'),
      desc: t('planDesc'),
      icon: IconAsk,
      badgeClass:
        'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800/60',
      dotClass: 'bg-amber-500',
    },
  }[tier] || {
    label: t('plan'),
    desc: t('planDesc'),
    icon: IconAsk,
    badgeClass: 'bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-900/40 dark:text-gray-400 dark:border-gray-800',
    dotClass: 'bg-gray-400',
  };

  const Icon = config.icon;

  return (
    <HoverCard openDelay={150} closeDelay={100}>
      <HoverCardTrigger asChild>
        <div
          className={cn(
            'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border cursor-pointer select-none transition-colors duration-150',
            config.badgeClass,
            className,
          )}
          data-testid={`deliverable-tier-badge-${tier.toLowerCase()}`}
        >
          <span className={cn('w-1.5 h-1.5 rounded-full', config.dotClass)} />
          <Icon className="w-3.5 h-3.5" />
          <span>{config.label}</span>
        </div>
      </HoverCardTrigger>
      <HoverCardContent align="start" sideOffset={6} className="w-80 p-3 text-xs">
        <div className="flex flex-col space-y-2">
          <div className="flex items-center gap-2 font-semibold text-foreground">
            <span className={cn('w-2 h-2 rounded-full', config.dotClass)} />
            <span>{config.label}</span>
          </div>
          <p className="text-muted-foreground leading-relaxed">{config.desc}</p>

          {evidence && (
            <div className="pt-2 border-t border-border/50 flex flex-col space-y-1.5">
              <span className="font-medium text-foreground/80">{t('evidenceDetails')}:</span>
              {evidence.verification_count !== undefined && evidence.verification_count > 0 && (
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>{t('verificationsPassed')}:</span>
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    {evidence.verification_count}
                  </Badge>
                </div>
              )}
              {evidence.files_written && evidence.files_written.length > 0 && (
                <div className="flex flex-col gap-0.5 text-muted-foreground">
                  <div className="flex items-center justify-between">
                    <span>{t('artifactsWritten')}:</span>
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                      {evidence.files_written.length}
                    </Badge>
                  </div>
                  <div className="max-h-20 overflow-y-auto pl-1 text-[11px] font-mono text-muted-foreground/80 space-y-0.5">
                    {evidence.files_written.slice(0, 5).map((f) => (
                      <div key={f} className="truncate" title={f}>
                        • {f}
                      </div>
                    ))}
                    {evidence.files_written.length > 5 && (
                      <div className="text-[10px] text-muted-foreground/60">
                        +{evidence.files_written.length - 5} more
                      </div>
                    )}
                  </div>
                </div>
              )}
              {evidence.sources_count !== undefined && evidence.sources_count > 0 && (
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>{t('sourcesConsulted')}:</span>
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    {evidence.sources_count}
                  </Badge>
                </div>
              )}
              {evidence.details && (
                <div className="text-[11px] text-muted-foreground/70 italic pt-1 truncate" title={evidence.details}>
                  {evidence.details}
                </div>
              )}
            </div>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
