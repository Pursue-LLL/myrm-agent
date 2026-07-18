'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { Brain, Search, Database } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { MemoryBriefData, MemoryBriefStatus } from '@/store/chat/types';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/primitives/hover-card';

interface MemoryInsightPanelProps {
  memoryBrief?: MemoryBriefData;
  memoryBriefStatus?: MemoryBriefStatus;
  memoryBudget?: { used: number; total: number };
  citations?: string[];
  className?: string;
}

function formatNamespaceLabel(
  namespace: string,
  t: ReturnType<typeof useTranslations>
): string {
  if (namespace === 'global') return t('namespaceGlobal');
  if (namespace.startsWith('agent:')) return t('namespaceAgent', { value: namespace.slice('agent:'.length) });
  if (namespace.startsWith('channel:')) return t('namespaceChannel', { value: namespace.slice('channel:'.length) });
  if (namespace.startsWith('conversation:')) return t('namespaceConversation');
  if (namespace.startsWith('task:')) return t('namespaceTask');
  if (namespace.startsWith('shared:')) return t('namespaceShared', { value: namespace.slice('shared:'.length) });
  return namespace;
}

export function resolveBriefUnavailableDescriptionKey(
  memoryBriefStatus?: MemoryBriefStatus
):
  | 'briefUnavailableDescription'
  | 'briefUnavailableDescriptionInjected'
  | 'briefUnavailableDescriptionNotInjected'
  | 'briefUnavailableDescriptionToolsMode'
  | 'briefUnavailableDescriptionAlreadyPresent'
  | 'briefUnavailableDescriptionSystemIssue' {
  const injection = memoryBriefStatus?.injection;
  if (injection?.state === 'applied') {
    return 'briefUnavailableDescriptionInjected';
  }
  if (injection?.state !== 'not_applied') {
    return 'briefUnavailableDescription';
  }
  if (injection.reason === 'already_present') {
    return 'briefUnavailableDescriptionAlreadyPresent';
  }
  if (injection.reason === 'recall_mode_tools') {
    return 'briefUnavailableDescriptionToolsMode';
  }
  if (injection.reason === 'missing_context' || injection.reason === 'not_injected') {
    return 'briefUnavailableDescriptionNotInjected';
  }
  if (
    injection.reason === 'load_error' ||
    injection.reason === 'static_error' ||
    injection.reason === 'invalid_static_payload' ||
    injection.reason === 'empty_context'
  ) {
    return 'briefUnavailableDescriptionSystemIssue';
  }
  return 'briefUnavailableDescription';
}

export default function MemoryInsightPanel({
  memoryBrief,
  memoryBriefStatus,
  memoryBudget,
  citations,
  className,
}: MemoryInsightPanelProps) {
  const t = useTranslations('memoryInsight');

  if (
    !memoryBrief &&
    memoryBriefStatus?.state !== 'skipped' &&
    !memoryBudget &&
    (!citations || citations.length === 0)
  ) {
    return null;
  }

  const memoryBriefUnavailable = !memoryBrief && memoryBriefStatus?.state === 'skipped';
  const briefUnavailableDescriptionKey = resolveBriefUnavailableDescriptionKey(memoryBriefStatus);
  const budgetPct = memoryBudget && memoryBudget.total > 0 ? Math.round((memoryBudget.used / memoryBudget.total) * 100) : 0;
  const briefNamespaceLabels = memoryBrief ? memoryBrief.namespaces.slice(0, 4).map((namespace) => formatNamespaceLabel(namespace, t)) : [];
  
  return (
    <div className={cn("flex flex-wrap items-center gap-2 mt-2", className)}>
      {/* Memory Brief Unavailable Pill */}
      {memoryBriefUnavailable && (
        <HoverCard openDelay={200}>
          <HoverCardTrigger asChild>
            <div className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-full bg-muted text-muted-foreground border border-border/70 cursor-help transition-colors hover:bg-muted/80">
              <Brain size={12} className="shrink-0 text-amber-500" />
              <span>{t('briefUnavailablePill')}</span>
            </div>
          </HoverCardTrigger>
          <HoverCardContent align="start" className="w-72 max-w-[calc(100vw-2rem)] p-3 z-50">
            <div className="space-y-2">
              <div className="text-xs font-semibold text-foreground">{t('briefUnavailableTitle')}</div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {t(briefUnavailableDescriptionKey)}
              </p>
            </div>
          </HoverCardContent>
        </HoverCard>
      )}

      {/* Memory Brief Pill */}
      {memoryBrief && (
        <HoverCard openDelay={200}>
          <HoverCardTrigger asChild>
            <div className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-full bg-primary/5 text-primary border border-primary/10 cursor-help transition-colors hover:bg-primary/10">
              <Brain size={12} className="shrink-0 text-primary" />
              <span>{t('briefPill')}</span>
            </div>
          </HoverCardTrigger>
          <HoverCardContent align="start" className="w-72 max-w-[calc(100vw-2rem)] p-3 z-50">
            <div className="space-y-2">
              <div className="text-xs font-semibold text-foreground">{t('briefTitle')}</div>
              {memoryBrief.is_cold_start ? (
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  {t('briefColdStartDescription')}
                </p>
              ) : (
                <>
                  {briefNamespaceLabels.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {briefNamespaceLabels.map((label) => (
                        <span
                          key={label}
                          className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-secondary text-secondary-foreground"
                        >
                          {label}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="text-[11px] text-muted-foreground leading-relaxed">
                    {t('briefStableSummary', {
                      instructions: memoryBrief.stable.instruction_count,
                      rules: memoryBrief.stable.rule_count,
                      profiles: memoryBrief.stable.profile_keys.length,
                    })}
                  </div>
                  <div className="text-[11px] text-muted-foreground leading-relaxed">
                    {t('briefLearnedSummary', {
                      preferences: memoryBrief.learned.preference_count,
                      rules: memoryBrief.learned.rule_count,
                      corrections: memoryBrief.learned.correction_count,
                    })}
                  </div>
                  {(memoryBrief.learned.preference_ids.length > 0 || memoryBrief.learned.rule_ids.length > 0) && (
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {memoryBrief.learned.preference_ids.map((id) => (
                        <span
                          key={`pref-${id}`}
                          className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-secondary text-secondary-foreground"
                        >
                          {t('briefPreferenceIdPrefix')}:{id}
                        </span>
                      ))}
                      {memoryBrief.learned.rule_ids.map((id) => (
                        <span
                          key={`rule-${id}`}
                          className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-secondary text-secondary-foreground"
                        >
                          {t('briefRuleIdPrefix')}:{id}
                        </span>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </HoverCardContent>
        </HoverCard>
      )}

      {/* Memory Budget Pill */}
      {memoryBudget && (
        <HoverCard openDelay={200}>
          <HoverCardTrigger asChild>
            <div className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-full bg-secondary/60 text-muted-foreground border border-border/50 cursor-help transition-colors hover:bg-secondary">
              <Brain size={12} className={cn("shrink-0", budgetPct > 80 ? "text-amber-500" : "text-primary/70")} />
              <span>{t('budgetPill', { pct: budgetPct })}</span>
            </div>
          </HoverCardTrigger>
          <HoverCardContent align="start" className="w-64 max-w-[calc(100vw-2rem)] p-3 z-50">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold">
                <span>{t('budgetTitle')}</span>
                <span className={budgetPct > 80 ? "text-amber-500" : ""}>{budgetPct}%</span>
              </div>
              <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                <div 
                  className={cn("h-full transition-all duration-500", budgetPct > 80 ? "bg-amber-500" : "bg-primary")}
                  style={{ width: `${Math.min(100, budgetPct)}%` }}
                />
              </div>
              <div className="text-[11px] text-muted-foreground flex justify-between">
                <span>{t('budgetUsed', { chars: memoryBudget.used.toLocaleString() })}</span>
                <span>{t('budgetLimit', { chars: memoryBudget.total.toLocaleString() })}</span>
              </div>
              <p className="text-[11px] text-muted-foreground mt-2 leading-relaxed">
                {t('budgetDescription')}
              </p>
            </div>
          </HoverCardContent>
        </HoverCard>
      )}

      {/* Citations Pill */}
      {citations && citations.length > 0 && (
        <HoverCard openDelay={200}>
          <HoverCardTrigger asChild>
            <div className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-full bg-primary/5 text-primary border border-primary/10 cursor-help transition-colors hover:bg-primary/10">
              <Search size={12} className="shrink-0" />
              <span>{t('citationsPill', { count: citations.length })}</span>
            </div>
          </HoverCardTrigger>
          <HoverCardContent align="start" className="w-64 max-w-[calc(100vw-2rem)] p-3 z-50">
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-foreground mb-1">
                <Database size={12} className="text-primary" />
                <span>{t('citationsTitle')}</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {t('citationsDescription')}
              </p>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {citations.map((id) => (
                  <span key={id} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-secondary text-secondary-foreground">
                    {id}
                  </span>
                ))}
              </div>
            </div>
          </HoverCardContent>
        </HoverCard>
      )}
    </div>
  );
}
