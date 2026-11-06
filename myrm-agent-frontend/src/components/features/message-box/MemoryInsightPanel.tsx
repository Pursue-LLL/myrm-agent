'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { Brain, Search, Database, PenLine } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { MemoryBriefData, MemoryBriefStatus } from '@/store/chat/types';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/primitives/hover-card';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { useMediaQuery } from '@/hooks/ui/useMediaQuery';
import { MemoryLifecycleTimeline } from '@/components/features/message-box/MemoryLifecycleTimeline';
import { hasVisibleLifecycle } from '@/components/features/message-box/memoryLifecyclePhases';
import { useMessageMemoryLifecycle } from '@/components/features/message-box/useMessageMemoryLifecycle';
import { retryChatMemoryExtract } from '@/services/chat';
import { ApiError } from '@/lib/api';

interface MemoryInsightPanelProps {
  chatId?: string | null;
  isLast?: boolean;
  isStreaming?: boolean;
  messageCreatedAtMs?: number;
  memoryBrief?: MemoryBriefData;
  memoryBriefStatus?: MemoryBriefStatus;
  memoryBudget?: {
    used: number;
    total: number;
    rulesConfigured?: number;
    rulesInjected?: number;
    rulesTruncated?: boolean;
  };
  citations?: string[];
  className?: string;
}

function formatNamespaceLabel(namespace: string, t: ReturnType<typeof useTranslations>): string {
  if (namespace === 'global') {
    return t('namespaceGlobal');
  }
  if (namespace.startsWith('agent:')) {
    return t('namespaceAgent', { value: namespace.slice('agent:'.length) });
  }
  if (namespace.startsWith('channel:')) {
    return t('namespaceChannel', { value: namespace.slice('channel:'.length) });
  }
  if (namespace.startsWith('conversation:')) {
    return t('namespaceConversation');
  }
  if (namespace.startsWith('task:')) {
    return t('namespaceTask');
  }
  if (namespace.startsWith('shared:')) {
    return t('namespaceShared', { value: namespace.slice('shared:'.length) });
  }
  return namespace;
}

export function resolveBriefUnavailableDescriptionKey(
  memoryBriefStatus?: MemoryBriefStatus,
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
    injection.reason === 'load_timeout' ||
    injection.reason === 'static_error' ||
    injection.reason === 'invalid_static_payload' ||
    injection.reason === 'empty_context'
  ) {
    return 'briefUnavailableDescriptionSystemIssue';
  }
  return 'briefUnavailableDescription';
}

export function resolveBriefStatusSourceKey(
  memoryBriefStatus?: MemoryBriefStatus,
): 'briefStatusSourcePreflight' | 'briefStatusSourceRuntimeFallback' | null {
  if (memoryBriefStatus?.state !== 'skipped') {
    return null;
  }
  if (memoryBriefStatus.source === 'runtime_fallback') {
    return 'briefStatusSourceRuntimeFallback';
  }
  if (memoryBriefStatus.source === 'preflight') {
    return 'briefStatusSourcePreflight';
  }
  return null;
}

interface InsightPillProps {
  /** Background, text, border and hover colours of the chip. */
  tone: string;
  icon: React.ReactNode;
  label: string;
  cardWidth?: 'w-64' | 'w-72';
  children: React.ReactNode;
}

/** Chip whose detail card opens on hover, or on tap where there is no hover: Radix HoverCard ignores touch pointers. */
function InsightPill({ tone, icon, label, cardWidth = 'w-72', children }: InsightPillProps) {
  const canHover = !useMediaQuery('(hover: none)');
  const chip = (
    <button
      type="button"
      className={cn(
        'flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-full border cursor-help transition-colors',
        tone,
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
  // collisionPadding mirrors the 1rem in max-w so a card shifted back into view never touches the screen edge.
  const contentProps = {
    align: 'start',
    collisionPadding: 16,
    className: cn(cardWidth, 'max-w-[calc(100vw-2rem)] p-3 z-50'),
  } as const;

  if (canHover) {
    return (
      <HoverCard openDelay={200}>
        <HoverCardTrigger asChild>{chip}</HoverCardTrigger>
        <HoverCardContent {...contentProps}>{children}</HoverCardContent>
      </HoverCard>
    );
  }
  return (
    <Popover>
      <PopoverTrigger asChild>{chip}</PopoverTrigger>
      <PopoverContent {...contentProps}>{children}</PopoverContent>
    </Popover>
  );
}

export default function MemoryInsightPanel({
  chatId,
  isLast = false,
  isStreaming = false,
  messageCreatedAtMs,
  memoryBrief,
  memoryBriefStatus,
  memoryBudget,
  citations,
  className,
}: MemoryInsightPanelProps) {
  const t = useTranslations('memoryInsight');
  const { phases, markExtractRetryPending } = useMessageMemoryLifecycle({
    chatId,
    messageCreatedAtMs,
    memoryBrief,
    memoryBriefStatus,
    citations,
    trackWriteExtract: Boolean(chatId) && isLast && !isStreaming,
  });

  const showWriteExtractTimeline = isLast && hasVisibleLifecycle(phases, { writeExtractOnly: true });
  const sessionOverrideCount = memoryBriefStatus?.session_ephemeral_delta_count ?? 0;
  const hasSessionOverrides = sessionOverrideCount > 0;

  if (
    !showWriteExtractTimeline &&
    !hasVisibleLifecycle(phases) &&
    !memoryBrief &&
    memoryBriefStatus?.state !== 'skipped' &&
    !memoryBudget &&
    !hasSessionOverrides &&
    (!citations || citations.length === 0)
  ) {
    return null;
  }

  const memoryBriefUnavailable = !memoryBrief && memoryBriefStatus?.state === 'skipped';
  const briefUnavailableDescriptionKey = resolveBriefUnavailableDescriptionKey(memoryBriefStatus);
  const briefStatusSourceKey = resolveBriefStatusSourceKey(memoryBriefStatus);
  const budgetPct =
    memoryBudget && memoryBudget.total > 0 ? Math.round((memoryBudget.used / memoryBudget.total) * 100) : 0;
  const briefNamespaceLabels = memoryBrief
    ? memoryBrief.namespaces.slice(0, 4).map((namespace) => formatNamespaceLabel(namespace, t))
    : [];

  return (
    <div className={cn('flex flex-col gap-2 mt-2', className)}>
      {isLast && phases.write.status === 'success' && (
        <p className="text-[11px] leading-relaxed text-muted-foreground">{t('sessionMemoryUpdatedHint')}</p>
      )}
      {showWriteExtractTimeline && (
        <MemoryLifecycleTimeline
          phases={phases}
          showRecall={false}
          onRetryExtract={
            chatId
              ? async () => {
                  try {
                    const result = await retryChatMemoryExtract(chatId);
                    if (result.status === 'already_in_flight') {
                      const { toast } = await import('@/lib/utils/toast');
                      toast.info(t('lifecycleRetryAlreadyInFlight'));
                      return;
                    }
                    markExtractRetryPending();
                  } catch (error) {
                    const { toast } = await import('@/lib/utils/toast');
                    const detail =
                      error instanceof ApiError && error.message.trim()
                        ? error.message.trim()
                        : t('lifecycleRetryFailed');
                    toast.warning(detail);
                  }
                }
              : undefined
          }
        />
      )}
      <div className="flex flex-wrap items-center gap-2">
        {/* Memory Brief Unavailable Pill */}
        {memoryBriefUnavailable && (
          <>
            <InsightPill
              tone="bg-muted text-muted-foreground border-border/70 hover:bg-muted/80"
              icon={<Brain size={12} className="shrink-0 text-amber-500" />}
              label={t('briefUnavailablePill')}
            >
              <div className="space-y-2">
                <div className="text-xs font-semibold text-foreground">{t('briefUnavailableTitle')}</div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">{t(briefUnavailableDescriptionKey)}</p>
                {briefStatusSourceKey && (
                  <p className="text-[11px] text-muted-foreground/90 leading-relaxed">{t(briefStatusSourceKey)}</p>
                )}
              </div>
            </InsightPill>
            <div className="w-full pl-1 space-y-1 md:hidden">
              <p className="text-[11px] leading-relaxed text-muted-foreground">{t(briefUnavailableDescriptionKey)}</p>
              {briefStatusSourceKey && (
                <p className="text-[11px] leading-relaxed text-muted-foreground/90">{t(briefStatusSourceKey)}</p>
              )}
            </div>
          </>
        )}

        {hasSessionOverrides && (
          <>
            <InsightPill
              tone="bg-secondary/80 text-secondary-foreground border-border/70 hover:bg-secondary"
              icon={<PenLine size={12} className="shrink-0 text-primary" />}
              label={t('sessionOverridePill')}
            >
              <div className="space-y-2">
                <div className="text-xs font-semibold text-foreground">{t('sessionOverrideTitle')}</div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">{t('sessionOverrideDescription')}</p>
              </div>
            </InsightPill>
            <p className="w-full pl-1 text-[11px] leading-relaxed text-muted-foreground md:hidden">
              {t('sessionOverrideMobile', { count: sessionOverrideCount })}
            </p>
          </>
        )}

        {/* Memory Brief Pill */}
        {memoryBrief && (
          <InsightPill
            tone="bg-primary/5 text-primary border-primary/10 hover:bg-primary/10"
            icon={<Brain size={12} className="shrink-0 text-primary" />}
            label={t('briefPill')}
          >
            <div className="space-y-2">
              <div className="text-xs font-semibold text-foreground">{t('briefTitle')}</div>
              {memoryBrief.is_cold_start ? (
                <p className="text-[11px] text-muted-foreground leading-relaxed">{t('briefColdStartDescription')}</p>
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
                      profiles: memoryBrief.stable.profile_count,
                    })}
                  </div>
                  {memoryBudget?.rulesTruncated === true &&
                    memoryBudget.rulesConfigured !== undefined &&
                    memoryBudget.rulesInjected !== undefined && (
                      <div className="text-[11px] leading-relaxed text-amber-500">
                        {t('briefRulesApplied', {
                          rules: memoryBudget.rulesConfigured,
                          injected: memoryBudget.rulesInjected,
                        })}
                      </div>
                    )}
                </>
              )}
            </div>
          </InsightPill>
        )}

        {/* Memory Budget Pill */}
        {memoryBudget && (
          <InsightPill
            tone="bg-secondary/60 text-muted-foreground border-border/50 hover:bg-secondary"
            icon={<Brain size={12} className={cn('shrink-0', budgetPct > 80 ? 'text-amber-500' : 'text-primary/70')} />}
            label={t('budgetPill', { pct: budgetPct })}
            cardWidth="w-64"
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold">
                <span>{t('budgetTitle')}</span>
                <span className={budgetPct > 80 ? 'text-amber-500' : ''}>{budgetPct}%</span>
              </div>
              <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                <div
                  className={cn('h-full transition-all duration-500', budgetPct > 80 ? 'bg-amber-500' : 'bg-primary')}
                  style={{ width: `${Math.min(100, budgetPct)}%` }}
                />
              </div>
              <div className="text-[11px] text-muted-foreground flex justify-between">
                <span>{t('budgetUsed', { chars: memoryBudget.used.toLocaleString() })}</span>
                <span>{t('budgetLimit', { chars: memoryBudget.total.toLocaleString() })}</span>
              </div>
              <p className="text-[11px] text-muted-foreground mt-2 leading-relaxed">{t('budgetDescription')}</p>
            </div>
          </InsightPill>
        )}

        {/* Citations Pill */}
        {citations && citations.length > 0 && (
          <InsightPill
            tone="bg-primary/5 text-primary border-primary/10 hover:bg-primary/10"
            icon={<Search size={12} className="shrink-0" />}
            label={t('citationsPill', { count: citations.length })}
            cardWidth="w-64"
          >
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-foreground mb-1">
                <Database size={12} className="text-primary" />
                <span>{t('citationsTitle')}</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">{t('citationsDescription')}</p>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {citations.map((id) => (
                  <span
                    key={id}
                    className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-secondary text-secondary-foreground"
                  >
                    {id}
                  </span>
                ))}
              </div>
            </div>
          </InsightPill>
        )}
      </div>
    </div>
  );
}
