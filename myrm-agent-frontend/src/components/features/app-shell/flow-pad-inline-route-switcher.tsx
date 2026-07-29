/**
 * [INPUT]
 * - AgentAvatar (POS: 智能体头像展示)
 * - TemplateListItem (POS: 专家模板 DTO)
 *
 * [OUTPUT]
 * - FlowPadInlineRouteSwitcher: Inline 路由切换与专家召唤菜单。
 *
 * [POS]
 * FlowPad 的 Inline 路由层 UI 子组件。承载“跟随当前会话 / 指定 Agent / 召唤专家模板”菜单，
 * 通过 props 与父组件解耦，避免主文件继续膨胀。
 */
import type { RefObject } from 'react';
import { Check, ChevronDown, Loader2, Search, Sparkles } from 'lucide-react';

import { AgentAvatar } from '@/components/agent/AgentAvatar';
import type { TemplateListItem } from '@/services/agent';

interface RouteAgentLite {
  id: string;
  name: string;
  avatar_url?: string | null;
}

interface InlineRouteSelectionLite {
  id: string;
}

interface FlowPadInlineRouteSwitcherProps {
  isInlineMode: boolean;
  isSubmitting: boolean;
  inlineRouteSwitching: boolean;
  inlineRouteSwitchError: string | null;
  currentAgentLabel: string;
  currentAgentId?: string;
  effectiveInlineRouteLabel: string;
  effectiveInlineRouteAvatar?: string;
  inlineRouteSelection: InlineRouteSelectionLite | null;
  agentRouteMenuOpen: boolean;
  setAgentRouteMenuOpen: (updater: boolean | ((open: boolean) => boolean)) => void;
  agentRouteMenuRef: RefObject<HTMLDivElement | null>;
  agentListLoading: boolean;
  availableAgents: RouteAgentLite[];
  templateSearchQuery: string;
  setTemplateSearchQuery: (value: string) => void;
  expertTemplatesLoading: boolean;
  expertTemplatesError: boolean;
  filteredExpertTemplates: TemplateListItem[];
  instantiatingTemplateId: string | null;
  onSelectInlineRouteAgent: (agentId: string | null) => Promise<boolean>;
  onFallbackToCurrentRoute: () => void;
  onLoadExpertTemplates: () => Promise<void>;
  onInstantiateExpertTemplate: (template: TemplateListItem, starterPrompt?: string) => Promise<void>;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export function FlowPadInlineRouteSwitcher({
  isInlineMode,
  isSubmitting,
  inlineRouteSwitching,
  inlineRouteSwitchError,
  currentAgentLabel,
  currentAgentId,
  effectiveInlineRouteLabel,
  effectiveInlineRouteAvatar,
  inlineRouteSelection,
  agentRouteMenuOpen,
  setAgentRouteMenuOpen,
  agentRouteMenuRef,
  agentListLoading,
  availableAgents,
  templateSearchQuery,
  setTemplateSearchQuery,
  expertTemplatesLoading,
  expertTemplatesError,
  filteredExpertTemplates,
  instantiatingTemplateId,
  onSelectInlineRouteAgent,
  onFallbackToCurrentRoute,
  onLoadExpertTemplates,
  onInstantiateExpertTemplate,
  t,
}: FlowPadInlineRouteSwitcherProps) {
  if (!isInlineMode) {
    return (
      <span className="text-[10px] text-muted-foreground/60">
        {t('sendTo')} <span className="font-medium text-muted-foreground">{currentAgentLabel}</span>
      </span>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground/60">{t('sendTo')}</span>
        <div className="relative" ref={agentRouteMenuRef}>
          <button
            type="button"
            data-testid="flowpad-inline-route-trigger"
            aria-expanded={agentRouteMenuOpen}
            disabled={isSubmitting || inlineRouteSwitching}
            className="inline-flex max-w-[320px] items-center gap-2 rounded-md border border-border/60 px-2 py-1 text-xs text-foreground transition-colors hover:bg-accent/40 disabled:opacity-60"
            onClick={() => setAgentRouteMenuOpen((open) => !open)}
          >
            <AgentAvatar
              url={effectiveInlineRouteAvatar}
              name={effectiveInlineRouteLabel}
              agentId={inlineRouteSelection?.id ?? currentAgentId}
              className="h-4 w-4"
              size="sm"
            />
            <span className="truncate">{effectiveInlineRouteLabel}</span>
            <span className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
              {inlineRouteSelection ? t('inlineRouteProfile') : t('inlineRouteCurrent')}
            </span>
            {inlineRouteSwitching ? (
              <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" />
            ) : (
              <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
            )}
          </button>
          {agentRouteMenuOpen && (
            <div className="absolute right-0 top-[calc(100%+6px)] z-50 w-[min(300px,calc(100vw-2rem))] rounded-md border border-border/60 bg-background p-1 shadow-xl">
              <div className="max-h-64 overflow-y-auto">
                <button
                  type="button"
                  data-testid="flowpad-inline-route-follow-current"
                  className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left text-xs hover:bg-accent/50"
                  onClick={() => void onSelectInlineRouteAgent(null)}
                >
                  <span className="truncate">{t('inlineRouteFollowCurrent', { agent: currentAgentLabel })}</span>
                  {!inlineRouteSelection && <Check className="h-3.5 w-3.5 text-primary" />}
                </button>
                {agentListLoading ? (
                  <p className="px-2 py-2 text-[11px] text-muted-foreground">{t('inlineRouteLoadingAgents')}</p>
                ) : availableAgents.length > 0 ? (
                  availableAgents.map((agent) => {
                    const selected = inlineRouteSelection?.id === agent.id;
                    return (
                      <button
                        key={agent.id}
                        type="button"
                        data-testid={`flowpad-inline-route-agent-${agent.id}`}
                        className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-xs hover:bg-accent/50"
                        onClick={() => void onSelectInlineRouteAgent(agent.id)}
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <AgentAvatar
                            url={agent.avatar_url}
                            name={agent.name}
                            agentId={agent.id}
                            className="h-4 w-4"
                            size="sm"
                          />
                          <span className="truncate">{agent.name}</span>
                        </span>
                        {selected && <Check className="h-3.5 w-3.5 text-primary" />}
                      </button>
                    );
                  })
                ) : (
                  <p className="px-2 py-2 text-[11px] text-muted-foreground">{t('inlineRouteNoAgents')}</p>
                )}

                <div className="mt-1 border-t border-border/50 pt-1.5">
                  <p className="px-2 pb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">
                    {t('inlineRouteTemplateSectionTitle')}
                  </p>
                  <div className="px-2 pb-1">
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground/60" />
                      <input
                        type="text"
                        value={templateSearchQuery}
                        aria-label={t('inlineRouteTemplateSearchPlaceholder')}
                        onChange={(event) => setTemplateSearchQuery(event.target.value)}
                        placeholder={t('inlineRouteTemplateSearchPlaceholder')}
                        className="h-7 w-full rounded-md border border-border/60 bg-background pl-6 pr-2 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/40"
                      />
                    </div>
                  </div>
                  {expertTemplatesLoading ? (
                    <p className="px-2 py-2 text-[11px] text-muted-foreground">
                      {t('inlineRouteTemplateLoading')}
                    </p>
                  ) : expertTemplatesError ? (
                    <button
                      type="button"
                      className="mx-2 my-1 w-[calc(100%-1rem)] rounded-sm border border-border/60 px-2 py-1.5 text-left text-[11px] text-muted-foreground hover:bg-accent/50"
                      onClick={() => void onLoadExpertTemplates()}
                    >
                      {t('inlineRouteTemplateRetry')}
                    </button>
                  ) : filteredExpertTemplates.length > 0 ? (
                    filteredExpertTemplates.map((template) => {
                      const isInstantiating = instantiatingTemplateId === template.id;
                      return (
                        <div key={template.id} className="px-1.5 pb-1">
                          <button
                            type="button"
                            data-testid={`flowpad-inline-template-${template.id}`}
                            disabled={isInstantiating || inlineRouteSwitching || isSubmitting}
                            className="flex w-full items-center justify-between gap-2 rounded-sm px-1 py-1.5 text-left text-xs hover:bg-accent/50 disabled:opacity-60"
                            onClick={() => void onInstantiateExpertTemplate(template)}
                          >
                            <span className="flex min-w-0 items-center gap-1.5">
                              <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary/80" />
                              <span className="truncate">{template.name}</span>
                            </span>
                            {isInstantiating ? (
                              <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" />
                            ) : (
                              <ChevronDown className="h-3 w-3 shrink-0 -rotate-90 text-muted-foreground" />
                            )}
                          </button>
                          {template.use_cases && template.use_cases.length > 0 && (
                            <div className="mt-0.5 flex flex-wrap gap-1 pl-5">
                              {template.use_cases.slice(0, 3).map((useCase, useCaseIndex) => (
                                <button
                                  key={useCase}
                                  type="button"
                                  data-testid={`flowpad-inline-template-usecase-${template.id}-${useCaseIndex}`}
                                  disabled={isInstantiating || inlineRouteSwitching || isSubmitting}
                                  onClick={() => void onInstantiateExpertTemplate(template, useCase)}
                                  className="rounded border border-primary/25 bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary hover:bg-primary/15 disabled:opacity-60"
                                >
                                  {useCase}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })
                  ) : (
                    <p className="px-2 py-2 text-[11px] text-muted-foreground">
                      {templateSearchQuery.trim()
                        ? t('inlineRouteTemplateNoResults')
                        : t('inlineRouteTemplateEmpty')}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      {inlineRouteSwitchError && (
        <div className="flex items-center justify-between gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1">
          <span className="truncate text-[10px] text-amber-700 dark:text-amber-300">
            {t('inlineRouteSwitchFailedHint', { agent: inlineRouteSwitchError })}
          </span>
          <button
            type="button"
            data-testid="flowpad-inline-route-fallback-current"
            className="shrink-0 text-[10px] font-medium text-amber-700 underline decoration-dotted underline-offset-2 dark:text-amber-300"
            onClick={onFallbackToCurrentRoute}
          >
            {t('inlineRouteFallbackAction')}
          </button>
        </div>
      )}
    </div>
  );
}
