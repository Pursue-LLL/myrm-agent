'use client';

/**
 * [INPUT]
 * - ensureLocalBackendReady (POS: 本地后端可用性探测)
 * - getTemplates / instantiateTemplate (POS: 模板列表与实例化 API)
 * - useChatStore.setInputMessage (POS: 会话输入草稿写入)
 *
 * [OUTPUT]
 * - TemplateMarket: 模板检索、展示与一键实例化入口
 *
 * [POS]
 * EmptyChat/AgentConfigPanel 的模板发现层组件。
 * 负责在不改动后端契约的前提下，把模板检索、团队场景召唤与会话预填闭环接入 GUI。
 */
import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ensureLocalBackendReady } from '@/lib/backend-health';
import { getTemplates, type TemplateListItem } from '@/services/agent';
import { cn } from '@/lib/utils/classnameUtils';
import { Bot, Plus, Loader2, Search, Users } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { resolveLucideIcon } from '@/components/agent/agent-icons';
import useChatStore from '@/store/useChatStore';
import {
  normalizeTemplateSearchText,
  resolveTemplateKind,
  templateMatchesSearchQuery,
} from '@/services/templateDiscovery';
import { recordExpertSummonSearchUsed, recordExpertSummonSurfaceViewed } from '@/services/expertSummonMetrics';
import { instantiateTemplateWithMetrics } from '@/services/templateSummon';
import { agentSettingsHref, teamAssetsHubHref } from '@/components/features/loadout/loadoutDeepLinks';

interface TemplateMarketProps {
  className?: string;
  onInstantiated?: (agentId: string) => void;
}

const renderAvatar = (avatarUrl: string | null | undefined, isTeam: boolean) => {
  if (avatarUrl?.startsWith('lucide:')) {
    const IconComponent = resolveLucideIcon(avatarUrl.slice(7));
    if (IconComponent) {
      return <IconComponent size={16} />;
    }
  }
  return isTeam ? <Users size={16} /> : <Bot size={16} />;
};

const TemplateMarket = ({ className, onInstantiated }: TemplateMarketProps) => {
  const t = useTranslations('agent.configPanel');
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [instantiatingId, setInstantiatingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const hasReportedSurfaceViewRef = useRef(false);
  const hasReportedSearchUseRef = useRef(false);
  const router = useRouter();
  const setInputMessage = useChatStore((state) => state.setInputMessage);

  useEffect(() => {
    let cancelled = false;

    const fetchTemplates = async () => {
      try {
        const backendReady = await ensureLocalBackendReady();
        if (!backendReady || cancelled) {
          return;
        }
        const data = await getTemplates();
        if (!cancelled) {
          setTemplates(data);
          if (data.length > 0 && !hasReportedSurfaceViewRef.current) {
            hasReportedSurfaceViewRef.current = true;
            recordExpertSummonSurfaceViewed('template_market', 'template-market');
          }
        }
      } catch {
        // Template market is optional; hide section when backend is unavailable.
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchTemplates();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const query = normalizeTemplateSearchText(searchQuery);
    if (!query || hasReportedSearchUseRef.current) {
      return;
    }
    hasReportedSearchUseRef.current = true;
    recordExpertSummonSearchUsed('template_market', query.length, 'template-market');
  }, [searchQuery]);

  const handleInstantiate = async (template: TemplateListItem, starterPrompt?: string) => {
    if (instantiatingId) {
      return;
    }
    const normalizedStarterPrompt = starterPrompt?.trim() ?? '';
    const fromSearch = normalizeTemplateSearchText(searchQuery).length > 0;
    const usedUseCase = normalizedStarterPrompt.length > 0;
    setInstantiatingId(template.id);
    try {
      const newAgent = await instantiateTemplateWithMetrics({
        templateId: template.id,
        surface: 'template_market',
        trigger: usedUseCase ? 'use_case_chip' : 'template_card',
        templateKind: resolveTemplateKind(template.agent_type),
        fromSearch,
        usedUseCase,
        contextKey: 'template-market',
      });
      if (normalizedStarterPrompt) {
        setInputMessage(normalizedStarterPrompt);
      }
      toast.success(t('instantiateSuccess') || 'Agent created from template!');
      if (onInstantiated) {
        onInstantiated(newAgent.id);
      } else if (template.agent_type === 'team') {
        router.push(teamAssetsHubHref());
      } else {
        router.push(agentSettingsHref(newAgent.id));
      }
    } catch (e) {
      console.error(e);
      toast.error(t('instantiateError') || 'Failed to instantiate template');
    } finally {
      setInstantiatingId(null);
    }
  };

  const filteredTemplates = useMemo(() => {
    return templates.filter((template) => templateMatchesSearchQuery(template, searchQuery));
  }, [searchQuery, templates]);

  if (loading) {
    return (
      <div className={cn('flex justify-center p-4', className)}>
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (templates.length === 0) {
    return null;
  }

  const individualTemplates = filteredTemplates.filter((item) => item.agent_type !== 'team');
  const teamTemplates = filteredTemplates.filter((item) => item.agent_type === 'team');

  return (
    <div className={cn('space-y-3 pt-2', className)}>
      <div className="flex items-center gap-2 px-1">
        <div className="flex-1 h-px bg-border/50" />
        <span className="text-xs text-muted-foreground">{t('templateMarket') || 'Template Market'}</span>
        <div className="flex-1 h-px bg-border/50" />
      </div>

      <div className="relative px-1">
        <Search
          size={12}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/70"
        />
        <input
          type="text"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          aria-label={t('searchMarketplace') || 'Search agents'}
          placeholder={t('searchMarketplace') || 'Search agents...'}
          className="h-8 w-full rounded-lg border border-border/60 bg-background pl-7 pr-2 text-xs text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary/40"
        />
      </div>

      {filteredTemplates.length === 0 && (
        <p className="px-1 text-xs text-muted-foreground/80">{t('noResults') || 'No agents found'}</p>
      )}

      {teamTemplates.length > 0 && (
        <div className="grid grid-cols-1 gap-3">
          {teamTemplates.map((template) => (
            <TeamTemplateCard
              key={template.id}
              template={template}
              instantiatingId={instantiatingId}
              onInstantiate={handleInstantiate}
            />
          ))}
        </div>
      )}

      {individualTemplates.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {individualTemplates.map((template) => (
            <button
              type="button"
              key={template.id}
              disabled={Boolean(instantiatingId)}
              className={cn(
                'relative flex flex-col gap-2 p-3 rounded-xl',
                'border border-border/40 bg-card/40 backdrop-blur-sm',
                'hover:border-primary/30 hover:bg-primary/5 transition-all text-left',
                'group cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                'disabled:opacity-60 disabled:cursor-not-allowed',
              )}
              onClick={() => void handleInstantiate(template)}
            >
              <div className="flex items-center gap-2">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 text-primary shrink-0">
                  {renderAvatar(template.avatar_url, false)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium text-foreground truncate">{template.name}</span>
                    {template.is_pareto_preset && (
                      <span className="shrink-0 px-1.5 py-0.2 text-[10px] font-medium rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        {template.cost_reduction_ratio
                          ? `-${Math.round(template.cost_reduction_ratio * 100)}%`
                          : 'Pareto'}
                      </span>
                    )}
                  </div>
                  {template.description && (
                    <div className="text-xs text-muted-foreground truncate">{template.description}</div>
                  )}
                </div>
                <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-background border border-border/50 opacity-0 group-hover:opacity-100 transition-opacity">
                  {instantiatingId === template.id ? (
                    <Loader2 size={12} className="animate-spin text-primary" />
                  ) : (
                    <Plus size={12} className="text-primary" />
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

function TeamTemplateCard({
  template,
  instantiatingId,
  onInstantiate,
}: {
  template: TemplateListItem;
  instantiatingId: string | null;
  onInstantiate: (template: TemplateListItem, starterPrompt?: string) => void;
}) {
  const isDisabled = Boolean(instantiatingId);

  return (
    <div
      role="button"
      tabIndex={isDisabled ? -1 : 0}
      aria-disabled={isDisabled}
      className={cn(
        'relative flex flex-col gap-2.5 p-3.5 rounded-xl',
        'border border-border/40 bg-card/40 backdrop-blur-sm',
        'hover:border-primary/30 hover:bg-primary/5 transition-all',
        'group cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
        isDisabled && 'opacity-60 cursor-not-allowed',
      )}
      onClick={() => {
        if (isDisabled) {
          return;
        }
        void onInstantiate(template);
      }}
      onKeyDown={(event) => {
        if (isDisabled) {
          return;
        }
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          void onInstantiate(template);
        }
      }}
    >
      <div className="flex items-center gap-2.5">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary/10 text-primary shrink-0">
          {renderAvatar(template.avatar_url, true)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-foreground truncate">{template.name}</span>
            <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded-md bg-primary/10 text-primary">
              Team
            </span>
            {template.is_pareto_preset && (
              <span className="shrink-0 px-1.5 py-0.2 text-[10px] font-medium rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                {template.cost_reduction_ratio
                  ? `-${Math.round(template.cost_reduction_ratio * 100)}%`
                  : 'Pareto'}
              </span>
            )}
          </div>
          {template.description && (
            <div className="text-xs text-muted-foreground line-clamp-1 mt-0.5">{template.description}</div>
          )}
        </div>
        <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-background border border-border/50 opacity-0 group-hover:opacity-100 transition-opacity">
          {instantiatingId === template.id ? (
            <Loader2 size={12} className="animate-spin text-primary" />
          ) : (
            <Plus size={12} className="text-primary" />
          )}
        </div>
      </div>

      {template.members && template.members.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-[46px]">
          {template.members.map((member, memberIndex) => (
            <span
              key={`${member.role}-${member.name}-${memberIndex}`}
              className="inline-flex items-center px-2 py-0.5 text-[11px] rounded-md bg-muted/60 text-muted-foreground"
            >
              {member.name}
            </span>
          ))}
        </div>
      )}

      {template.use_cases && template.use_cases.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-[46px]">
          {template.use_cases.map((useCase, useCaseIndex) => (
            <button
              key={`${useCase}-${useCaseIndex}`}
              type="button"
              disabled={isDisabled}
              onClick={(event) => {
                event.stopPropagation();
                void onInstantiate(template, useCase);
              }}
              className="inline-flex items-center rounded-md border border-primary/25 bg-primary/10 px-2 py-0.5 text-[11px] text-primary hover:bg-primary/15 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {useCase}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default memo(TemplateMarket);
