/**
 * [INPUT]
 * - ./templateTypes::*
 * - ./useTemplateMarketplaceStore::useTemplateMarketplaceStore
 * - ./AgentTemplateCard::AgentTemplateCard
 * - ./ZeroPromptCloneWorkbench::ZeroPromptCloneWorkbench
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - AgentTemplateMarketplace: Full marketplace view for prebuilt agent app discovery and zero-prompt instantiation
 *
 * [POS]
 * Primary container for Item 32 marketplace feature.
 * Strictly adheres to 0-any rule, < 400 lines limit, and zero native emoji.
 */

'use client';

import React, { useEffect, useMemo, memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Search,
  Sparkles,
  Layers,
  Code2,
  Briefcase,
  ShoppingCart,
  Users,
  Compass,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import type { TemplateCategory, AgentTemplateItem } from './templateTypes';
import { useTemplateMarketplaceStore } from './useTemplateMarketplaceStore';
import { AgentTemplateCard } from './AgentTemplateCard';
import { ZeroPromptCloneWorkbench } from './ZeroPromptCloneWorkbench';

interface AgentTemplateMarketplaceProps {
  onAgentCreated?: (agent: { id: string; name: string }) => void;
  className?: string;
}

const CATEGORY_TABS: Array<{ key: TemplateCategory; icon: React.ComponentType<{ className?: string }> }> = [
  { key: 'all', icon: Layers },
  { key: 'engineering', icon: Code2 },
  { key: 'office', icon: Briefcase },
  { key: 'commerce', icon: ShoppingCart },
  { key: 'team', icon: Users },
  { key: 'general', icon: Compass },
];

export const AgentTemplateMarketplace = memo<AgentTemplateMarketplaceProps>(({ onAgentCreated, className }) => {
  const t = useTranslations('templateMarketplace');

  const templates = useTemplateMarketplaceStore((s) => s.templates);
  const isLoading = useTemplateMarketplaceStore((s) => s.isLoading);
  const error = useTemplateMarketplaceStore((s) => s.error);
  const searchQuery = useTemplateMarketplaceStore((s) => s.searchQuery);
  const selectedCategory = useTemplateMarketplaceStore((s) => s.selectedCategory);
  const fetchTemplates = useTemplateMarketplaceStore((s) => s.fetchTemplates);
  const setSearchQuery = useTemplateMarketplaceStore((s) => s.setSearchQuery);
  const setSelectedCategory = useTemplateMarketplaceStore((s) => s.setSelectedCategory);

  useEffect(() => {
    if (templates.length === 0 && !isLoading) {
      void fetchTemplates();
    }
  }, [fetchTemplates, templates.length, isLoading]);

  const filteredTemplates = useMemo(() => {
    return templates.filter((item: AgentTemplateItem) => {
      // Category filter
      if (selectedCategory !== 'all') {
        const matchesCategory =
          selectedCategory === 'team'
            ? item.agent_type === 'team' || item.category === 'team'
            : item.category === selectedCategory;
        if (!matchesCategory) {
          return false;
        }
      }

      // Query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const inName = item.name.toLowerCase().includes(q);
        const inDesc = item.description?.toLowerCase().includes(q) ?? false;
        const inCat = item.category.toLowerCase().includes(q);
        const inCases = item.use_cases?.some((uc) => uc.toLowerCase().includes(q)) ?? false;
        if (!inName && !inDesc && !inCat && !inCases) {
          return false;
        }
      }

      return true;
    });
  }, [templates, selectedCategory, searchQuery]);

  return (
    <section
      data-testid="agent-template-marketplace"
      aria-label={t('title')}
      className={`w-full space-y-6 ${className || ''}`}
    >
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-zinc-200 dark:border-zinc-800">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-amber-500" />
            <h2 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
              {t('title')}
            </h2>
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
            {t('subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
          <span className="font-semibold text-zinc-800 dark:text-zinc-200">{templates.length}</span>
          <span>{t('stats.total')}</span>
          <button
            type="button"
            onClick={() => void fetchTemplates()}
            disabled={isLoading}
            aria-label="Refresh templates"
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors ml-1"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Search and Category Filter Toolbar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        {/* Search input */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className="w-full rounded-lg border border-zinc-200 bg-white pl-9 pr-3 py-1.5 text-xs text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100 dark:focus:border-zinc-400"
          />
        </div>

        {/* Category Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          {CATEGORY_TABS.map((tab) => {
            const TabIcon = tab.icon;
            const isSelected = selectedCategory === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setSelectedCategory(tab.key)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors whitespace-nowrap ${
                  isSelected
                    ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 shadow-xs'
                    : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800'
                }`}
              >
                <TabIcon className="h-3 w-3" />
                <span>{t(`categories.${tab.key}`)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Grid Content / Loading / Error / Empty States */}
      {isLoading && templates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-400">
          <Loader2 className="h-8 w-8 animate-spin mb-3 text-zinc-500" />
          <p className="text-xs">{t('workbench.cloning')}</p>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-200 bg-red-50/50 p-6 text-center text-xs text-red-600 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-400">
          <p>{error}</p>
          <button
            type="button"
            onClick={() => void fetchTemplates()}
            className="mt-3 inline-flex items-center gap-1 rounded-md bg-red-100 px-3 py-1 font-medium text-red-700 hover:bg-red-200 dark:bg-red-900/60 dark:text-red-300"
          >
            <RefreshCw className="h-3 w-3" />
            <span>Retry</span>
          </button>
        </div>
      ) : filteredTemplates.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-200 bg-zinc-50/50 py-16 text-center dark:border-zinc-800 dark:bg-zinc-900/20">
          <Layers className="mx-auto h-8 w-8 text-zinc-300 dark:text-zinc-600 mb-2" />
          <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
            {t('empty.title')}
          </h3>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 max-w-sm mx-auto">
            {t('empty.description')}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTemplates.map((template) => (
            <AgentTemplateCard key={template.id} template={template} />
          ))}
        </div>
      )}

      {/* Modal Mount */}
      <ZeroPromptCloneWorkbench onSuccess={onAgentCreated} />
    </section>
  );
});

AgentTemplateMarketplace.displayName = 'AgentTemplateMarketplace';
