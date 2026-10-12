/**
 * [INPUT]
 * - ./templateTypes::AgentTemplateItem
 * - ./useTemplateMarketplaceStore::useTemplateMarketplaceStore
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - AgentTemplateCard: Semantic card component rendering template details and trigger clone
 *
 * [POS]
 * Card view in Prebuilt Agent App Marketplace.
 * Strictly adheres to 0-any rule, < 400 lines limit, and zero native emoji.
 */

'use client';

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Users,
  Bot,
  Sparkles,
  Zap,
  Wrench,
  BookOpen,
  TrendingDown,
  ChevronRight,
  Briefcase,
  Code2,
  ShoppingCart,
  Compass,
} from 'lucide-react';
import type { AgentTemplateItem } from './templateTypes';
import { useTemplateMarketplaceStore } from './useTemplateMarketplaceStore';

interface AgentTemplateCardProps {
  template: AgentTemplateItem;
}

function getCategoryIcon(category: string): React.ReactElement {
  switch (category) {
    case 'engineering':
      return <Code2 className="h-4 w-4 text-sky-500" />;
    case 'office':
      return <Briefcase className="h-4 w-4 text-amber-500" />;
    case 'commerce':
      return <ShoppingCart className="h-4 w-4 text-emerald-500" />;
    case 'team':
      return <Users className="h-4 w-4 text-indigo-500" />;
    default:
      return <Compass className="h-4 w-4 text-zinc-400" />;
  }
}

export const AgentTemplateCard = memo<AgentTemplateCardProps>(({ template }) => {
  const t = useTranslations('templateMarketplace');
  const openCloneWorkbench = useTemplateMarketplaceStore((s) => s.openCloneWorkbench);

  const isTeam = template.agent_type === 'team';
  const toolsCount = template.settings_preview?.enabled_builtin_tools.length ?? 0;
  const skillsCount =
    (template.settings_preview?.skill_ids.length ?? 0) +
    (template.settings_preview?.prebuilt_skill_ids.length ?? 0);

  return (
    <article
      data-testid={`template-card-${template.id}`}
      className="group relative flex flex-col justify-between rounded-xl border border-zinc-200 bg-white p-5 shadow-xs transition-all hover:border-zinc-300 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700"
    >
      <div>
        {/* Header: Type icon & Badges */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-100 dark:bg-zinc-800">
              {isTeam ? (
                <Users className="h-5 w-5 text-indigo-500" />
              ) : (
                <Bot className="h-5 w-5 text-sky-500" />
              )}
            </div>
            <div>
              <h3 className="font-semibold text-zinc-900 dark:text-zinc-100 text-base leading-snug line-clamp-1">
                {template.name}
              </h3>
              <div className="flex items-center gap-1.5 mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                {getCategoryIcon(template.category)}
                <span className="capitalize">{template.category}</span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {isTeam ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                <Users className="h-3 w-3" />
                {t('card.team')}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-700 dark:bg-sky-950/60 dark:text-sky-300">
                <Bot className="h-3 w-3" />
                {t('card.individual')}
              </span>
            )}
            {template.is_pareto_preset && (
              <span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                <TrendingDown className="h-3 w-3" />
                Pareto
              </span>
            )}
          </div>
        </div>

        {/* Description */}
        <p className="text-xs text-zinc-600 dark:text-zinc-400 line-clamp-2 min-h-8 mb-3 leading-relaxed">
          {template.description || t('subtitle')}
        </p>

        {/* Capability Indicators */}
        <div className="flex flex-wrap items-center gap-2 mb-3 text-xs text-zinc-500 dark:text-zinc-400">
          <span className="inline-flex items-center gap-1 rounded bg-zinc-100 px-1.5 py-0.5 dark:bg-zinc-800">
            <Wrench className="h-3 w-3 text-zinc-400" />
            {toolsCount} {t('card.builtinTools')}
          </span>
          <span className="inline-flex items-center gap-1 rounded bg-zinc-100 px-1.5 py-0.5 dark:bg-zinc-800">
            <BookOpen className="h-3 w-3 text-zinc-400" />
            {skillsCount} {t('card.skills')}
          </span>
          {typeof template.cost_reduction_ratio === 'number' && (
            <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
              <Sparkles className="h-3 w-3" />
              -{(template.cost_reduction_ratio * 100).toFixed(0)}%
            </span>
          )}
        </div>

        {/* Use Case Pills */}
        {template.use_cases && template.use_cases.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {template.use_cases.slice(0, 3).map((useCase, idx) => (
              <span
                key={idx}
                className="inline-block rounded-md border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-[11px] text-zinc-600 dark:border-zinc-800 dark:bg-zinc-800/60 dark:text-zinc-300 line-clamp-1"
              >
                {useCase}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Action footer */}
      <div className="pt-3 border-t border-zinc-100 dark:border-zinc-800/80 flex items-center justify-between">
        <span className="text-[11px] text-zinc-400">
          {isTeam && template.members ? `${template.members.length} members` : 'Zero-Prompt Ready'}
        </span>
        <button
          type="button"
          onClick={() => openCloneWorkbench(template)}
          data-testid={`clone-btn-${template.id}`}
          className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white shadow-xs transition-colors hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Zap className="h-3.5 w-3.5 text-amber-400 fill-amber-400" />
          <span>{t('card.cloneAction')}</span>
          <ChevronRight className="h-3 w-3" />
        </button>
      </div>
    </article>
  );
});

AgentTemplateCard.displayName = 'AgentTemplateCard';
