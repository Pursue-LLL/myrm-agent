'use client';

/**
 * [INPUT]
 * @/store/memory::MemoryType (POS: memory types)
 * next-intl::useTranslations (POS: i18n)
 *
 * [OUTPUT]
 * MemoryScopeHierarchyCard: Interactive visual card showcasing the 4 memory scopes (Task, Conversation, Agent, Global)
 * with lifecycle, boundary definitions, and prompt cache persistence rules.
 *
 * [POS]
 * Visual educational and governance component placed in MemorySection and MemoryCommandCenter.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import {
  IconCheck,
  IconClock,
  IconMessageSquare,
  IconCpu,
  IconGlobe,
  IconShieldCheck,
} from '@/components/features/icons/PremiumIcons';

export type MemoryScopeLevel = 'task' | 'conversation' | 'agent' | 'global';

interface ScopeDefinition {
  level: MemoryScopeLevel;
  icon: typeof IconGlobe;
  titleKey: string;
  scopeTagKey: string;
  lifecycleKey: string;
  descKey: string;
  badgeClass: string;
}

const SCOPES: ScopeDefinition[] = [
  {
    level: 'task',
    icon: IconClock,
    titleKey: 'scopeHierarchy.task.title',
    scopeTagKey: 'scopeHierarchy.task.tag',
    lifecycleKey: 'scopeHierarchy.task.lifecycle',
    descKey: 'scopeHierarchy.task.desc',
    badgeClass: 'border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400',
  },
  {
    level: 'conversation',
    icon: IconMessageSquare,
    titleKey: 'scopeHierarchy.conversation.title',
    scopeTagKey: 'scopeHierarchy.conversation.tag',
    lifecycleKey: 'scopeHierarchy.conversation.lifecycle',
    descKey: 'scopeHierarchy.conversation.desc',
    badgeClass: 'border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-400',
  },
  {
    level: 'agent',
    icon: IconCpu,
    titleKey: 'scopeHierarchy.agent.title',
    scopeTagKey: 'scopeHierarchy.agent.tag',
    lifecycleKey: 'scopeHierarchy.agent.lifecycle',
    descKey: 'scopeHierarchy.agent.desc',
    badgeClass: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  },
  {
    level: 'global',
    icon: IconGlobe,
    titleKey: 'scopeHierarchy.global.title',
    scopeTagKey: 'scopeHierarchy.global.tag',
    lifecycleKey: 'scopeHierarchy.global.lifecycle',
    descKey: 'scopeHierarchy.global.desc',
    badgeClass: 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400',
  },
];

interface MemoryScopeHierarchyCardProps {
  activeLevel?: MemoryScopeLevel | null;
  onSelectLevel?: (level: MemoryScopeLevel) => void;
  className?: string;
  compact?: boolean;
}

export const MemoryScopeHierarchyCard = memo<MemoryScopeHierarchyCardProps>(
  ({ activeLevel, onSelectLevel, className, compact = false }) => {
    const t = useTranslations('memory');

    return (
      <div
        className={cn(
          'rounded-xl border border-border/50 bg-background/60 p-4 backdrop-blur-sm transition-all',
          className,
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/40 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <IconShieldCheck className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {t('scopeHierarchy.cardTitle', { default: 'Memory Scope Hierarchy' })}
              </h3>
              <p className="text-xs text-muted-foreground">
                {t('scopeHierarchy.cardSubtitle', {
                  default: 'Visual boundary & lifecycle management for agent long-term knowledge',
                })}
              </p>
            </div>
          </div>
          <span className="rounded-full border border-border/60 bg-accent/40 px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {t('scopeHierarchy.fourTiersBadge', { default: '4-Tier Unified Scopes' })}
          </span>
        </div>

        <div
          className={cn(
            'mt-3.5 grid gap-2.5',
            compact ? 'grid-cols-2 lg:grid-cols-4' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
          )}
        >
          {SCOPES.map((scope) => {
            const Icon = scope.icon;
            const isSelected = activeLevel === scope.level;

            return (
              <button
                type="button"
                key={scope.level}
                onClick={() => onSelectLevel?.(scope.level)}
                disabled={!onSelectLevel}
                className={cn(
                  'group relative flex flex-col justify-between rounded-lg border p-3 text-left transition-all',
                  onSelectLevel ? 'cursor-pointer hover:border-primary/40 hover:bg-accent/30' : 'cursor-default',
                  isSelected
                    ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                    : 'border-border/50 bg-background/80',
                )}
              >
                <div>
                  <div className="flex items-center justify-between gap-1.5">
                    <div className="flex items-center gap-1.5">
                      <Icon className="h-3.5 w-3.5 text-muted-foreground group-hover:text-foreground" />
                      <span className="text-xs font-semibold text-foreground">{t(scope.titleKey)}</span>
                    </div>
                    <span className={cn('rounded-full border px-1.5 py-0.2 text-[10px] font-medium', scope.badgeClass)}>
                      {t(scope.scopeTagKey)}
                    </span>
                  </div>

                  <div className="mt-1.5 text-[11px] font-medium text-primary/80">{t(scope.lifecycleKey)}</div>

                  <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{t(scope.descKey)}</p>
                </div>

                {isSelected && (
                  <div className="mt-2 flex items-center gap-1 text-[10px] font-medium text-primary">
                    <IconCheck className="h-3 w-3" />
                    <span>{t('scopeHierarchy.selected', { default: 'Selected' })}</span>
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    );
  },
);

MemoryScopeHierarchyCard.displayName = 'MemoryScopeHierarchyCard';

export default MemoryScopeHierarchyCard;
