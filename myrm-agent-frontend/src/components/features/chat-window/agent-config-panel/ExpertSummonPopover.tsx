'use client';

/**
 * [INPUT]
 * - @/services/agent::getTemplates, TemplateListItem (POS: 专家与团队模板 DTO)
 * - @/services/templateDiscovery::templateMatchesSearchQuery, resolveTemplateKind (POS: 模板搜索与类型判定)
 * - @/services/templateSummon::instantiateTemplateWithMetrics (POS: 专家召唤统一入口与漏斗埋点)
 * - @/store/useChatStore::useChatStore (POS: 状态与输入框草稿同步)
 *
 * [OUTPUT]
 * - ExpertSummonPopover: 输入框工具栏的专家团队一键发现与召唤 Popover 浮层
 *
 * [POS]
 * MessageInput 工具栏中的专家发现入口，支持即时预览与召唤闭环。
 */

import { memo, useEffect, useState, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Users, Bot, Search, Plus, Loader2, Sparkles, X } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import { getTemplates, type TemplateListItem } from '@/services/agent';
import { templateMatchesSearchQuery, resolveTemplateKind } from '@/services/templateDiscovery';
import { instantiateTemplateWithMetrics } from '@/services/templateSummon';
import { recordExpertSummonSearchUsed, recordExpertSummonSurfaceViewed } from '@/services/expertSummonMetrics';
import useChatStore from '@/store/useChatStore';

export interface ExpertSummonPopoverProps {
  className?: string;
  onSummoned?: (agentId: string) => void;
}

export const ExpertSummonPopover = memo(function ExpertSummonPopover({
  className,
  onSummoned,
}: ExpertSummonPopoverProps) {
  const t = useTranslations('expertSummon');
  const [open, setOpen] = useState(false);
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [summoningId, setSummoningId] = useState<string | null>(null);
  const router = useRouter();
  const setInputMessage = useChatStore((state) => state.setInputMessage);

  useEffect(() => {
    if (!open) {
      return;
    }
    recordExpertSummonSurfaceViewed('flow_pad_inline');
    let active = true;
    const fetchList = async () => {
      setLoading(true);
      try {
        const data = await getTemplates();
        if (active) {
          setTemplates(data);
        }
      } catch {
        if (active) {
          setTemplates([]);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void fetchList();
    return () => {
      active = false;
    };
  }, [open]);

  const handleSearchChange = (val: string) => {
    setSearchQuery(val);
    if (val.trim()) {
      recordExpertSummonSearchUsed('flow_pad_inline', val.length);
    }
  };

  const filteredTemplates = useMemo(() => {
    return templates.filter((tpl) => templateMatchesSearchQuery(tpl, searchQuery));
  }, [templates, searchQuery]);

  const handleSummon = useCallback(
    async (template: TemplateListItem, useCase?: string) => {
      if (summoningId) {
        return;
      }
      setSummoningId(template.id);
      try {
        const newAgent = await instantiateTemplateWithMetrics({
          templateId: template.id,
          surface: 'flow_pad_inline',
          trigger: useCase ? 'use_case_chip' : 'template_card',
          templateKind: resolveTemplateKind(template.agent_type),
          fromSearch: Boolean(searchQuery.trim()),
          usedUseCase: Boolean(useCase),
        });

        toast.success(t('summonSuccess', { name: template.name }));
        if (useCase) {
          setInputMessage(useCase);
        } else if (template.use_cases && template.use_cases.length > 0) {
          setInputMessage(template.use_cases[0]);
        }
        setOpen(false);
        onSummoned?.(newAgent.id);
        router.push(`/chat?agentId=${newAgent.id}`);
      } catch {
        toast.error(t('summonFailed'));
      } finally {
        setSummoningId(null);
      }
    },
    [summoningId, searchQuery, t, setInputMessage, onSummoned, router],
  );

  return (
    <div className={cn('relative inline-flex items-center', className)}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          'flex h-7 items-center gap-1.5 rounded-md border border-border/80 bg-background/80 px-2 text-xs font-medium text-foreground transition-all hover:border-primary/50 hover:bg-muted/80 active:scale-95 shadow-2xs',
          open && 'border-primary text-primary bg-primary/5',
        )}
        title={t('featuredTitle')}
        aria-label={t('featuredTitle')}
        data-testid="expert-summon-popover-trigger"
      >
        <Users size={13} className="text-primary" />
        <span className="hidden sm:inline">{t('teamBadge')}</span>
        <Plus size={12} className="opacity-70" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden="true" />
          <div
            data-testid="expert-summon-popover-menu"
            className="absolute bottom-full mb-2 left-0 z-50 flex w-72 sm:w-80 flex-col rounded-xl border border-border bg-popover/95 p-3 text-popover-foreground shadow-xl backdrop-blur-md animate-in fade-in zoom-in-95 duration-150"
          >
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/60">
              <div className="flex items-center gap-1.5 text-xs font-semibold">
                <Sparkles size={13} className="text-primary" />
                <span>{t('featuredTitle')}</span>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-xs p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X size={13} />
              </button>
            </div>

            <div className="relative mb-2">
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder={t('searchPlaceholder')}
                className="w-full rounded-md border border-border/70 bg-secondary/50 py-1 pl-7 pr-2 text-xs outline-hidden focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
              />
            </div>

            <div className="max-h-60 overflow-y-auto space-y-1.5 pr-1 [scrollbar-width:thin]">
              {loading ? (
                <div className="flex items-center justify-center py-6 text-xs text-muted-foreground">
                  <Loader2 size={14} className="animate-spin mr-1.5 text-primary" />
                  {t('loading')}
                </div>
              ) : filteredTemplates.length === 0 ? (
                <div className="py-6 text-center text-xs text-muted-foreground">{t('empty')}</div>
              ) : (
                filteredTemplates.map((template) => {
                  const isTeam = template.agent_type === 'team';
                  const isSummoning = summoningId === template.id;

                  return (
                    <div
                      key={template.id}
                      className="group flex flex-col rounded-lg border border-border/50 bg-card/60 p-2 transition-colors hover:border-primary/40 hover:bg-primary/5"
                    >
                      <div className="flex items-start justify-between gap-1.5">
                        <div className="flex items-center gap-1.5">
                          {isTeam ? (
                            <Users size={14} className="text-indigo-500 shrink-0" />
                          ) : (
                            <Bot size={14} className="text-emerald-500 shrink-0" />
                          )}
                          <span className="text-xs font-medium text-foreground">{template.name}</span>
                          <span className="rounded-xs bg-muted px-1 py-0.2 text-[9px] text-muted-foreground">
                            {isTeam ? t('teamBadge') : t('expertBadge')}
                          </span>
                        </div>
                        <button
                          type="button"
                          disabled={Boolean(summoningId)}
                          onClick={() => void handleSummon(template)}
                          className="inline-flex h-5 items-center gap-1 rounded-sm bg-primary/10 px-1.5 text-[10px] font-medium text-primary transition-colors hover:bg-primary hover:text-primary-foreground disabled:opacity-50"
                        >
                          {isSummoning ? <Loader2 size={10} className="animate-spin" /> : <Plus size={10} />}
                          {t('summonButton')}
                        </button>
                      </div>

                      {template.description && (
                        <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{template.description}</p>
                      )}

                      {template.use_cases && template.use_cases.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {template.use_cases.slice(0, 2).map((uc, i) => (
                            <button
                              key={i}
                              type="button"
                              disabled={Boolean(summoningId)}
                              onClick={() => void handleSummon(template, uc)}
                              className="inline-flex max-w-[200px] truncate rounded-xs border border-border/40 bg-background/50 px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:border-primary/30 hover:text-primary"
                              title={uc}
                            >
                              💡 {uc}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
});
