'use client';

/**
 * [INPUT]
 * - @/services/agent::getTemplates, TemplateListItem (POS: 模板列表获取与结构)
 * - @/services/templateSummon::instantiateTemplateWithMetrics (POS: 专家召唤统一入口与漏斗埋点)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态与输入框预填)
 *
 * [OUTPUT]
 * - FeaturedExpertChips: 输入框上方的精选专家小队与顾问快捷推荐条
 *
 * [POS]
 * MessageInput / FlowPad 输入框区域的专家团队发现与快捷召唤组件。
 */

import { memo, useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Bot, Sparkles, Users, X, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import { getTemplates, type TemplateListItem } from '@/services/agent';
import { resolveTemplateKind } from '@/services/templateDiscovery';
import { instantiateTemplateWithMetrics } from '@/services/templateSummon';
import useChatStore from '@/store/useChatStore';

export interface FeaturedExpertChipsProps {
  className?: string;
  onSummoned?: (agentId: string) => void;
}

export const FeaturedExpertChips = memo(function FeaturedExpertChips({
  className,
  onSummoned,
}: FeaturedExpertChipsProps) {
  const t = useTranslations('expertSummon');
  const [featuredTemplates, setFeaturedTemplates] = useState<TemplateListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [summoningId, setSummoningId] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const router = useRouter();
  const setInputMessage = useChatStore((state) => state.setInputMessage);

  useEffect(() => {
    let active = true;
    const fetchFeatured = async () => {
      setLoading(true);
      try {
        const templates = await getTemplates();
        if (active) {
          // 挑选最多 4 个精选团队或 Pareto 预设模板
          const featured = templates
            .filter((tpl) => tpl.agent_type === 'team' || tpl.is_pareto_preset)
            .slice(0, 4);
          setFeaturedTemplates(featured);
        }
      } catch {
        if (active) {
          setFeaturedTemplates([]);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void fetchFeatured();
    return () => {
      active = false;
    };
  }, []);

  const handleSummon = useCallback(
    async (template: TemplateListItem) => {
      if (summoningId) {
        return;
      }
      setSummoningId(template.id);
      try {
        const newAgent = await instantiateTemplateWithMetrics({
          templateId: template.id,
          surface: 'flow_pad_inline',
          trigger: 'use_case_chip',
          templateKind: resolveTemplateKind(template.agent_type),
          fromSearch: false,
          usedUseCase: false,
        });

        toast.success(t('summonSuccess', { name: template.name }));
        if (template.use_cases && template.use_cases.length > 0) {
          setInputMessage(template.use_cases[0]);
        }
        onSummoned?.(newAgent.id);
        router.push(`/chat?agentId=${newAgent.id}`);
      } catch {
        toast.error(t('summonFailed'));
      } finally {
        setSummoningId(null);
      }
    },
    [summoningId, t, setInputMessage, onSummoned, router],
  );

  if (dismissed || loading || featuredTemplates.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="featured-expert-chips"
      className={cn(
        'mb-2 flex flex-wrap items-center gap-1.5 rounded-lg border border-border/50 bg-secondary/30 px-2.5 py-1.5 backdrop-blur-xs',
        className,
      )}
    >
      <span className="flex items-center gap-1 text-xs font-medium text-muted-foreground shrink-0 mr-1">
        <Sparkles size={13} className="text-primary animate-pulse" />
        {t('featuredTitle')}
      </span>

      {featuredTemplates.map((template) => {
        const isTeam = template.agent_type === 'team';
        const isSummoning = summoningId === template.id;

        return (
          <button
            key={template.id}
            type="button"
            disabled={Boolean(summoningId)}
            onClick={() => void handleSummon(template)}
            className={cn(
              'inline-flex h-6 items-center gap-1.5 rounded-md border border-border/80 bg-background/80 px-2 text-xs font-medium text-foreground transition-all hover:border-primary/40 hover:bg-primary/5 hover:text-primary active:scale-95 disabled:opacity-50 disabled:pointer-events-none shadow-2xs',
              isSummoning && 'border-primary text-primary',
            )}
            title={template.description ?? template.name}
          >
            {isSummoning ? (
              <Loader2 size={12} className="animate-spin text-primary" />
            ) : isTeam ? (
              <Users size={12} className="text-indigo-500" />
            ) : (
              <Bot size={12} className="text-emerald-500" />
            )}
            <span className="max-w-[120px] truncate">{template.name}</span>
            <span className="rounded-xs bg-muted/80 px-1 py-0.2 text-[10px] text-muted-foreground">
              {isTeam ? t('teamBadge') : t('expertBadge')}
            </span>
          </button>
        );
      })}

      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="ml-auto inline-flex size-5 items-center justify-center rounded-sm text-muted-foreground/60 transition-colors hover:bg-muted hover:text-foreground"
        aria-label="Close featured experts"
      >
        <X size={12} />
      </button>
    </div>
  );
});
