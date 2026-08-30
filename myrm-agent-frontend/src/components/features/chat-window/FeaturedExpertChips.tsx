'use client';

/**
 * [INPUT]
 * - @/services/agent::getTemplates, TemplateListItem (POS: 模板列表获取)
 * - @/services/templateSummon::instantiateTemplateWithMetrics (POS: 带度量指标的模板实例化)
 * - @/services/templateDiscovery::resolveTemplateKind (POS: 模板类型识别)
 * - @/services/expertSummonMetrics::recordExpertSummonSurfaceViewed (POS: 曝光上报)
 * - @/store/useChatStore (POS: 聊天状态总线)
 *
 * [OUTPUT]
 * - FeaturedExpertChips: EmptyChat 首屏 Featured 专家/团队芯片组件。
 *
 * [POS]
 * 空聊天界面专家发现层。提供通用工作向 squads / 行业专家的一键召唤与开聊闭环。
 */

import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Users, Bot, Sparkles, Loader2, ArrowUpRight } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import { ensureLocalBackendReady } from '@/lib/backend-health';
import { getTemplates, type TemplateListItem } from '@/services/agent';
import { resolveLucideIcon } from '@/components/agent/agent-icons';
import { resolveTemplateKind } from '@/services/templateDiscovery';
import { instantiateTemplateWithMetrics } from '@/services/templateSummon';
import { recordExpertSummonSurfaceViewed } from '@/services/expertSummonMetrics';
import useChatStore from '@/store/useChatStore';

interface FeaturedExpertChipsProps {
  className?: string;
}

const renderAvatar = (avatarUrl: string | null | undefined, isTeam: boolean) => {
  if (avatarUrl?.startsWith('lucide:')) {
    const IconComponent = resolveLucideIcon(avatarUrl.slice(7));
    if (IconComponent) {
      return <IconComponent size={15} />;
    }
  }
  return isTeam ? <Users size={15} /> : <Bot size={15} />;
};

export const FeaturedExpertChips = memo(function FeaturedExpertChips({ className }: FeaturedExpertChipsProps) {
  const t = useTranslations('expertSummon');
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [summoningId, setSummoningId] = useState<string | null>(null);
  const hasReportedViewRef = useRef(false);

  const setAgentConfig = useChatStore((state) => state.setAgentConfig);
  const setInputMessage = useChatStore((state) => state.setInputMessage);

  useEffect(() => {
    let cancelled = false;

    const loadFeatured = async () => {
      try {
        const backendReady = await ensureLocalBackendReady();
        if (!backendReady || cancelled) {
          return;
        }
        const allTemplates = await getTemplates();
        if (!cancelled) {
          // Prioritize teams and templates with rich use_cases or Pareto presets
          const featured = allTemplates
            .sort((a, b) => {
              if (a.agent_type === 'team' && b.agent_type !== 'team') return -1;
              if (a.agent_type !== 'team' && b.agent_type === 'team') return 1;
              if (a.is_pareto_preset && !b.is_pareto_preset) return -1;
              if (!a.is_pareto_preset && b.is_pareto_preset) return 1;
              return (b.use_cases?.length ?? 0) - (a.use_cases?.length ?? 0);
            })
            .slice(0, 5);

          setTemplates(featured);
          if (featured.length > 0 && !hasReportedViewRef.current) {
            hasReportedViewRef.current = true;
            recordExpertSummonSurfaceViewed('empty_chat_featured', 'empty-chat:featured');
          }
        }
      } catch {
        // Soft fail
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadFeatured();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleSummon = useCallback(
    async (template: TemplateListItem) => {
      if (summoningId) {
        return;
      }
      setSummoningId(template.id);
      const starterPrompt = template.use_cases?.[0]?.trim() ?? '';
      try {
        const newAgent = await instantiateTemplateWithMetrics({
          templateId: template.id,
          surface: 'empty_chat_featured',
          trigger: 'featured_chip',
          templateKind: resolveTemplateKind(template.agent_type),
          fromSearch: false,
          usedUseCase: starterPrompt.length > 0,
          contextKey: 'empty-chat:featured',
        });

        // Bind new agent to active session
        setAgentConfig(newAgent);
        if (starterPrompt) {
          setInputMessage(starterPrompt);
        }
        toast.success(t('summonSuccess', { name: template.name }));
      } catch (err) {
        console.error('Failed to summon featured expert:', err);
        toast.error(t('summonFailed'));
      } finally {
        setSummoningId(null);
      }
    },
    [summoningId, setAgentConfig, setInputMessage, t],
  );

  if (loading || templates.length === 0) {
    return null;
  }

  return (
    <div className={cn('w-full flex flex-col items-center gap-2.5 my-1 animate-in fade-in duration-300', className)}>
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium">
        <Sparkles className="w-3.5 h-3.5 text-primary/70" />
        <span>{t('featuredTitle')}</span>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2 max-w-full">
        {templates.map((tpl) => {
          const isTeam = tpl.agent_type === 'team';
          const isSummoning = summoningId === tpl.id;

          return (
            <button
              key={tpl.id}
              type="button"
              disabled={Boolean(summoningId)}
              onClick={() => void handleSummon(tpl)}
              className={cn(
                'group relative inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium',
                'border border-border/80 bg-background/80 hover:bg-accent/70 hover:border-primary/40',
                'transition-all duration-200 shadow-xs hover:shadow-sm cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed',
                isTeam && 'border-primary/20 bg-primary/5 hover:bg-primary/10',
              )}
              title={tpl.description || tpl.name}
            >
              <span
                className={cn(
                  'flex items-center justify-center w-5 h-5 rounded-full text-muted-foreground group-hover:text-primary transition-colors',
                  isTeam ? 'bg-primary/15 text-primary' : 'bg-muted',
                )}
              >
                {isSummoning ? (
                  <Loader2 className="w-3 h-3 animate-spin text-primary" />
                ) : (
                  renderAvatar(tpl.avatar_url, isTeam)
                )}
              </span>
              <span className="truncate max-w-[140px] text-foreground/90 group-hover:text-foreground font-medium">
                {tpl.name}
              </span>
              <span
                className={cn(
                  'px-1.5 py-0.2 rounded text-[10px] uppercase font-semibold tracking-wider',
                  isTeam
                    ? 'bg-primary/20 text-primary-foreground/90 dark:text-primary'
                    : 'bg-muted text-muted-foreground',
                )}
              >
                {isTeam ? t('teamBadge') : t('expertBadge')}
              </span>
              <ArrowUpRight className="w-3 h-3 text-muted-foreground/50 opacity-0 group-hover:opacity-100 group-hover:text-primary transition-all -ml-0.5" />
            </button>
          );
        })}
      </div>
    </div>
  );
});

FeaturedExpertChips.displayName = 'FeaturedExpertChips';
export default FeaturedExpertChips;
