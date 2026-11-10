'use client';

/**
 * [INPUT]
 * - @/services/featuredTemplates::loadFeaturedTemplates, peekFeaturedTemplates (POS: 精选模板（60 秒缓存 + 共享请求）)
 * - @/services/templateSummon::instantiateTemplateWithMetrics (POS: 专家召唤统一入口与漏斗埋点)
 * - @/hooks/ui/useProactiveDismissal::useProactiveDismissed, isProactiveDismissed, dismissProactive (POS: 主动推荐卡片的关闭记忆)
 * - @/store/useChatStore::useChatStore (POS: 会话是否为空)
 * - ./prefillComposerWithUseCase (POS: 召唤后预填输入框且不覆盖草稿)
 *
 * [OUTPUT]
 * - FeaturedExpertChips: 输入框上方的精选专家小队与顾问快捷推荐条
 *
 * [POS]
 * MessageInput 输入框区域的专家团队发现与快捷召唤组件，只在空会话出现：已有对话的会话里它既不相关，
 * 每次切换会话还会重新请求模板。任何宽度下都是单行（放不下时横向滑动并有渐隐），高度与芯片名称无关，
 * 所以加载期的等高占位和成品是同一个盒子，数据到达时不挪动输入框；请求失败则整条不显示。
 * 关闭（×）按设备永久记住，不会在下一个新会话里再冒出来，已关闭时连模板请求都不发。
 */

import { memo, useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Bot, Users, X, Loader2 } from 'lucide-react';
import { UsersThree } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import { useScrollEdgeFade } from '@/hooks/ui/useScrollEdgeFade';
import { dismissProactive, isProactiveDismissed, useProactiveDismissed } from '@/hooks/ui/useProactiveDismissal';
import type { TemplateListItem } from '@/services/agentTemplates';
import { loadFeaturedTemplates, peekFeaturedTemplates } from '@/services/featuredTemplates';
import { resolveTemplateKind } from '@/services/templateDiscovery';
import { instantiateTemplateWithMetrics, extractSummonErrorMessage } from '@/services/templateSummon';
import useChatStore from '@/store/useChatStore';
import { prefillComposerWithUseCase } from './prefillComposerWithUseCase';

const DISMISS_KEY = 'featured-experts';
const STRIP_CLASS =
  'mb-2 flex items-center gap-1.5 rounded-lg border border-border/50 bg-secondary/30 px-2.5 py-1.5 backdrop-blur-xs';
const SKELETON_CHIP_WIDTHS = ['w-24', 'w-28', 'w-20'] as const;

export interface FeaturedExpertChipsProps {
  className?: string;
  onSummoned?: (agentId: string) => void;
}

type StripData = { status: 'loading' } | { status: 'ready'; templates: TemplateListItem[] } | { status: 'unavailable' };

function initialStripData(): StripData {
  const cached = peekFeaturedTemplates();
  return cached ? { status: 'ready', templates: cached } : { status: 'loading' };
}

/** Same box as the loaded strip (chip row plus the close button), so the composer does not move when data arrives. */
function StripSkeleton({ className }: { className?: string }) {
  return (
    <div data-testid="featured-expert-chips-skeleton" aria-hidden="true" className={cn(STRIP_CLASS, className)}>
      <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
        {SKELETON_CHIP_WIDTHS.map((width) => (
          <span key={width} className={cn('h-8 shrink-0 rounded-lg bg-muted/70 sm:h-6', width)} />
        ))}
      </div>
      <span className="size-8 shrink-0 sm:size-6" />
    </div>
  );
}

export const FeaturedExpertChips = memo(function FeaturedExpertChips({
  className,
  onSummoned,
}: FeaturedExpertChipsProps) {
  const t = useTranslations('expertSummon');
  const isEmptyConversation = useChatStore((state) => state.messages.length === 0);
  const dismissed = useProactiveDismissed(DISMISS_KEY);
  const [data, setData] = useState<StripData>(initialStripData);
  const [summoningId, setSummoningId] = useState<string | null>(null);
  const router = useRouter();
  const stripFadeRef = useScrollEdgeFade<HTMLDivElement>();

  const visible = isEmptyConversation && !dismissed;
  const needsLoad = visible && data.status === 'loading';

  useEffect(() => {
    // The hydration pass renders "not dismissed" (the server cannot read storage), so ask the real memory before
    // spending a request on a strip that is about to disappear.
    if (!needsLoad || isProactiveDismissed(DISMISS_KEY)) {
      return;
    }
    let active = true;
    loadFeaturedTemplates().then(
      (templates) => {
        if (active) {
          setData({ status: 'ready', templates });
        }
      },
      () => {
        if (active) {
          setData({ status: 'unavailable' });
        }
      },
    );
    return () => {
      active = false;
    };
  }, [needsLoad]);

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
        prefillComposerWithUseCase(template.use_cases?.[0]);
        onSummoned?.(newAgent.id);
        router.push(`/chat?agentId=${newAgent.id}`);
      } catch (err) {
        toast.error(extractSummonErrorMessage(err, t('summonFailed')));
      } finally {
        setSummoningId(null);
      }
    },
    [summoningId, t, onSummoned, router],
  );

  if (!visible || data.status === 'unavailable') {
    return null;
  }
  if (data.status === 'loading') {
    return <StripSkeleton className={className} />;
  }
  if (data.templates.length === 0) {
    return null;
  }

  return (
    <div data-testid="featured-expert-chips" className={cn(STRIP_CLASS, className)}>
      {/* A single swipeable row at every width: its height never depends on the chip names, so the placeholder above
          is the same box and the composer cannot move when the chips arrive. A faded edge shows that more chips sit
          out of view. The title is only the leading icon (its text stays for assistive tech and the tooltip) so the
          chips get the row's width. */}
      <div
        ref={stripFadeRef}
        className="scroll-fade-x flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto scrollbar-hide"
      >
        <span className="mr-1 flex shrink-0 items-center text-primary" title={t('featuredTitle')}>
          <UsersThree size={14} weight="duotone" aria-hidden="true" />
          <span className="sr-only">{t('featuredTitle')}</span>
        </span>

        {data.templates.map((template) => {
          const isTeam = template.agent_type === 'team';
          const isSummoning = summoningId === template.id;

          return (
            <button
              key={template.id}
              type="button"
              disabled={Boolean(summoningId)}
              onClick={() => void handleSummon(template)}
              className={cn(
                'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-border/80 bg-background/80 px-2 text-xs font-medium text-foreground transition-all hover:border-primary/40 hover:bg-primary/5 hover:text-primary active:scale-95 disabled:opacity-50 disabled:pointer-events-none shadow-2xs sm:h-6',
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
              <span className="max-w-[8rem] truncate sm:max-w-[10rem]">{template.name}</span>
              <span className="rounded-xs bg-muted/80 px-1 py-0.2 text-[10px] text-muted-foreground">
                {isTeam ? t('teamBadge') : t('expertBadge')}
              </span>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        onClick={() => dismissProactive(DISMISS_KEY)}
        className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm text-muted-foreground/60 transition-colors hover:bg-muted hover:text-foreground sm:size-6"
        aria-label={t('featuredDismiss')}
      >
        <X size={12} />
      </button>
    </div>
  );
});
