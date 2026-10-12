'use client';

/**
 * [INPUT]
 * - FleetCockpitSummary, AgentState from @/services/sessionMap
 * - Translation strings from 'sessionMap' namespace
 * - User filter / search callbacks
 *
 * [OUTPUT]
 * - AgentFleetCockpit: Cockpit header strip with aggregate metrics, search bar, and state filter tabs
 *
 * [POS]
 * Fleet overview cockpit dashboard for Project-Centric Session Map and Fleet Management.
 * Strict typing: Zero `any`. File length < 280 lines. Zero native emoji.
 */

import { useId } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconSearch,
  IconX,
  IconActivity,
  IconFolder,
  IconSparkles,
  IconCheck,
} from '@/components/features/icons/PremiumIcons';
import type { FleetCockpitSummary, AgentState } from '@/services/sessionMap';

export interface AgentFleetCockpitProps {
  summary: FleetCockpitSummary | null;
  activeFilter?: AgentState;
  onFilterChange: (state?: AgentState) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  viewMode: 'topology' | 'list';
  onViewModeChange: (mode: 'topology' | 'list') => void;
}

const FILTER_TABS: Array<{ id: AgentState | 'all'; labelKey: string; colorClass: string }> = [
  { id: 'all', labelKey: 'filterAll', colorClass: 'bg-primary/20 text-primary' },
  { id: 'working', labelKey: 'filterWorking', colorClass: 'bg-emerald-500/20 text-emerald-500' },
  { id: 'ready', labelKey: 'filterReady', colorClass: 'bg-blue-500/20 text-blue-500' },
  { id: 'waiting_input', labelKey: 'filterWaiting', colorClass: 'bg-amber-500/20 text-amber-500' },
  { id: 'error', labelKey: 'filterError', colorClass: 'bg-rose-500/20 text-rose-500' },
];

export function AgentFleetCockpit({
  summary,
  activeFilter,
  onFilterChange,
  searchQuery,
  onSearchChange,
  viewMode,
  onViewModeChange,
}: AgentFleetCockpitProps) {
  const t = useTranslations('sessionMap');
  const searchInputId = useId();

  return (
    <div className="flex flex-col gap-3 p-4 rounded-2xl bg-card border border-border/80 shadow-md">
      {/* Top Metrics Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 text-xs">
        {/* Total Projects */}
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-muted/40 border border-border/40">
          <IconFolder className="w-4 h-4 text-primary shrink-0" />
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground">{t('metricProjects')}</span>
            <span className="font-bold text-sm text-foreground">{summary?.total_projects ?? 0}</span>
          </div>
        </div>

        {/* Working Agents */}
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
          <div className="relative w-3.5 h-3.5 flex items-center justify-center">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">
              {t('metricWorking')}
            </span>
            <span className="font-bold text-sm text-emerald-700 dark:text-emerald-300">
              {summary?.working_agents ?? 0}
            </span>
          </div>
        </div>

        {/* Ready Standby */}
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-blue-500/10 border border-blue-500/20">
          <IconCheck className="w-4 h-4 text-blue-500 shrink-0" />
          <div className="flex flex-col">
            <span className="text-[10px] text-blue-600 dark:text-blue-400 font-medium">
              {t('metricReady')}
            </span>
            <span className="font-bold text-sm text-blue-700 dark:text-blue-300">
              {summary?.ready_agents ?? 0}
            </span>
          </div>
        </div>

        {/* Awaiting Input */}
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20">
          <IconActivity className="w-4 h-4 text-amber-500 shrink-0" />
          <div className="flex flex-col">
            <span className="text-[10px] text-amber-600 dark:text-amber-400 font-medium">
              {t('metricWaiting')}
            </span>
            <span className="font-bold text-sm text-amber-700 dark:text-amber-300">
              {summary?.waiting_input_agents ?? 0}
            </span>
          </div>
        </div>

        {/* Blocked / Error */}
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20">
          <IconX className="w-4 h-4 text-rose-500 shrink-0" />
          <div className="flex flex-col">
            <span className="text-[10px] text-rose-600 dark:text-rose-400 font-medium">
              {t('metricErrors')}
            </span>
            <span className="font-bold text-sm text-rose-700 dark:text-rose-300">
              {summary?.error_agents ?? 0}
            </span>
          </div>
        </div>

        {/* Token Consumption */}
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-muted/40 border border-border/40">
          <IconSparkles className="w-4 h-4 text-amber-400 shrink-0" />
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground">{t('metricTokens')}</span>
            <span className="font-mono font-bold text-sm text-foreground">
              {summary?.total_tokens_consumed
                ? `${Math.round(summary.total_tokens_consumed / 1000)}k`
                : '0'}
            </span>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-1 border-t border-border/60">
        {/* State Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          {FILTER_TABS.map((tab) => {
            const isSelected =
              tab.id === 'all' ? activeFilter === undefined : activeFilter === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onFilterChange(tab.id === 'all' ? undefined : tab.id)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors border ${
                  isSelected
                    ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                    : 'bg-muted/40 text-muted-foreground border-border/60 hover:bg-muted'
                }`}
              >
                {t(tab.labelKey)}
              </button>
            );
          })}
        </div>

        {/* Search & View Mode Switcher */}
        <div className="flex items-center gap-2">
          {/* Instant Search Input */}
          <div className="relative flex-1 sm:w-60">
            <IconSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
            <input
              id={searchInputId}
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="w-full pl-8 pr-7 py-1.5 rounded-xl bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => onSearchChange('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-muted-foreground hover:text-foreground"
                aria-label={t('clearSearch')}
              >
                <IconX className="w-3 h-3" />
              </button>
            )}
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center p-0.5 rounded-xl bg-muted/60 border border-border/60 text-xs">
            <button
              type="button"
              onClick={() => onViewModeChange('topology')}
              className={`px-2.5 py-1 rounded-lg font-medium transition-colors ${
                viewMode === 'topology'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t('viewTopology')}
            </button>
            <button
              type="button"
              onClick={() => onViewModeChange('list')}
              className={`px-2.5 py-1 rounded-lg font-medium transition-colors ${
                viewMode === 'list'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t('viewList')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
