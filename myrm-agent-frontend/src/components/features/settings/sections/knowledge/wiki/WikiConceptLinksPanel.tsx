'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 六语言文案，命名空间 settings.wiki.concepts.links)
 * - @/services/wikiService::wikiService (POS: Wiki REST 客户端，提供 getConceptLinks 词条链接与拓扑网络检索)
 * - @/components/primitives/button::Button (POS: 基础按钮组件)
 * - @/lib/utils/classnameUtils::cn (POS: 类名合并工具)
 *
 * [OUTPUT]
 * - WikiConceptLinksPanel: 词条双向链接与局部微型拓扑雷达面板，呈现反向引用（含上下文切片）、前置引用与局部图谱
 *
 * [POS]
 * 词条脉络导航组件。嵌入词条详情抽屉，展示词条的入链、出链及 Ego 拓扑图，支持点击直达关联词条。
 */

import { useEffect, useState, useTransition, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowUpRight, CornerDownLeft, Network, FileText, AlertCircle, RefreshCw, type LucideIcon } from 'lucide-react';
import { wikiService, type ConceptLinksResponse, type ConceptLinkItem } from '@/services/wikiService';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';

interface WikiConceptLinksPanelProps {
  conceptName: string;
  agentId?: string | null;
  onSelectConcept?: (name: string, heading?: string | null) => void;
}

type LinksTab = 'backlinks' | 'outlinks' | 'ego';

export function WikiConceptLinksPanel({ conceptName, agentId, onSelectConcept }: WikiConceptLinksPanelProps) {
  const t = useTranslations('settings.wiki.concepts.links');
  const [linksData, setLinksData] = useState<ConceptLinksResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<LinksTab>('backlinks');
  const [, startTransition] = useTransition();

  const fetchLinks = useCallback(async () => {
    if (!conceptName) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await wikiService.getConceptLinks(conceptName, 1, agentId);
      setLinksData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '');
    } finally {
      setLoading(false);
    }
  }, [conceptName, agentId]);

  useEffect(() => {
    fetchLinks();
  }, [fetchLinks]);

  if (loading && !linksData) {
    return (
      <div className="rounded-lg border border-border/60 bg-muted/10 p-4 animate-pulse space-y-2">
        <div className="h-4 bg-muted/40 rounded w-1/3" />
        <div className="h-8 bg-muted/20 rounded w-full" />
      </div>
    );
  }

  const outlinks = linksData?.outlinks ?? [];
  const backlinks = linksData?.backlinks ?? [];
  const egoNodes = linksData?.ego_graph?.nodes ?? [];
  const egoEdges = linksData?.ego_graph?.edges ?? [];
  // 首次加载失败时没有数据，不能把「0 条」与空态当事实展示给用户
  const visibleTab = linksData ? activeTab : null;
  const tabs: ReadonlyArray<{ id: LinksTab; label: string; Icon: LucideIcon; iconClass: string }> = [
    {
      id: 'backlinks',
      label: t('tabBacklinks', { count: backlinks.length }),
      Icon: CornerDownLeft,
      iconClass: 'text-sky-500',
    },
    {
      id: 'outlinks',
      label: t('tabOutlinks', { count: outlinks.length }),
      Icon: ArrowUpRight,
      iconClass: 'text-emerald-500',
    },
    { id: 'ego', label: t('tabNearby', { count: egoNodes.length }), Icon: Network, iconClass: 'text-indigo-500' },
  ];

  return (
    <div
      id="wiki-concept-links"
      className="@container rounded-xl border border-border/70 bg-card/60 backdrop-blur-sm p-4 space-y-4 shadow-sm"
    >
      {/* 头部导航与统计胶囊：面板嵌在宽度不定的详情栏里，按面板自身宽度（容器查询）而不是视口宽度适配 */}
      <div className="space-y-3 border-b border-border/50 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
            <Network className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold tracking-tight text-foreground">{t('title')}</span>
            {linksData && (
              <span className="text-[11px] px-2 py-0.5 rounded-full font-mono bg-primary/10 text-primary border border-primary/20">
                {t('summary', { backlinks: backlinks.length, outlinks: outlinks.length })}
              </span>
            )}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={fetchLinks}
            className="h-6 w-6 shrink-0 p-0 text-muted-foreground hover:text-foreground"
            title={t('refresh')}
            aria-label={t('refresh')}
          >
            <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />
          </Button>
        </div>

        {/* 视图切换按钮组：等分整行，放不下时在条内横向滚动 */}
        {linksData && (
          <div className="flex w-full items-center gap-1 overflow-x-auto scrollbar-hide bg-muted/40 p-0.5 rounded-lg border border-border/40 text-xs">
            {tabs.map(({ id, label, Icon, iconClass }) => (
              <button
                type="button"
                key={id}
                onClick={() => setActiveTab(id)}
                className={cn(
                  'flex flex-1 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-2 py-1 font-medium transition-all @md:px-3',
                  activeTab === id
                    ? 'bg-background text-foreground shadow-xs border border-border/60'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <Icon className={cn('hidden w-3.5 h-3.5 @md:block', iconClass)} />
                <span>{label}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {error !== null && (
        <div className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/20 p-2.5 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error || t('loadFailed')}</span>
        </div>
      )}

      {/* Tab 1: 反向链接（Backlinks） */}
      {visibleTab === 'backlinks' && (
        <div className="space-y-2">
          {backlinks.length === 0 ? (
            <p className="text-xs text-muted-foreground py-3 text-center">{t('emptyBacklinks')}</p>
          ) : (
            <div className="grid grid-cols-1 gap-2">
              {backlinks.map((link: ConceptLinkItem) => (
                <button
                  type="button"
                  key={link.name}
                  disabled={!link.exists || !onSelectConcept}
                  onClick={() => {
                    if (link.exists && onSelectConcept) {
                      startTransition(() => onSelectConcept(link.name, link.heading));
                    }
                  }}
                  className={cn(
                    'group w-full rounded-lg border p-2.5 transition-all text-left flex flex-col gap-1',
                    link.exists
                      ? 'border-border/60 bg-muted/15 hover:bg-muted/30 hover:border-primary/40 cursor-pointer focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring'
                      : 'border-dashed border-amber-500/30 bg-amber-500/5 cursor-default',
                  )}
                >
                  <div className="flex min-w-0 items-center gap-1.5 font-medium text-xs text-foreground group-hover:text-primary transition-colors">
                    <FileText className="w-3.5 h-3.5 text-sky-500 shrink-0" />
                    <span className="truncate">{link.name}</span>
                    {!link.exists && (
                      <span className="shrink-0 text-[10px] px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                        {t('missing')}
                      </span>
                    )}
                  </div>

                  {link.heading && (
                    <span
                      title={t('jumpToSection', { heading: link.heading })}
                      className="mt-0.5 self-start text-[10px] px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground border border-border/50 font-mono truncate max-w-[220px]"
                    >
                      § {link.heading}
                    </span>
                  )}

                  {link.context_snippet && (
                    <span className="text-[11px] text-muted-foreground bg-background/50 border border-border/40 rounded px-2 py-1 leading-relaxed font-mono line-clamp-2 block">
                      &ldquo;{link.context_snippet}&rdquo;
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: 引用前置（Outlinks） */}
      {visibleTab === 'outlinks' && (
        <div className="space-y-2">
          {outlinks.length === 0 ? (
            <p className="text-xs text-muted-foreground py-3 text-center">{t('emptyOutlinks')}</p>
          ) : (
            <div className="grid grid-cols-1 gap-2 @md:grid-cols-2">
              {outlinks.map((link: ConceptLinkItem) => (
                <button
                  type="button"
                  key={link.name}
                  disabled={!link.exists || !onSelectConcept}
                  onClick={() => {
                    if (link.exists && onSelectConcept) {
                      startTransition(() => onSelectConcept(link.name));
                    }
                  }}
                  className={cn(
                    'group w-full rounded-lg border p-2.5 transition-all text-left flex items-center justify-between gap-2',
                    link.exists
                      ? 'border-border/60 bg-muted/15 hover:bg-muted/30 hover:border-emerald-500/40 cursor-pointer focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring'
                      : 'border-dashed border-amber-500/30 bg-amber-500/5 cursor-default',
                  )}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <ArrowUpRight className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                    <span className="text-xs font-medium text-foreground truncate group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                      {link.name}
                    </span>
                  </div>
                  {!link.exists && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 shrink-0">
                      {t('missing')}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 3: 局部拓扑微型雷达（Ego Graph） */}
      {visibleTab === 'ego' && (
        <div className="space-y-3">
          <div className="rounded-lg border border-border/60 bg-muted/20 p-3 min-h-[120px] flex flex-wrap items-center justify-center gap-2">
            {egoNodes.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('emptyNearby')}</p>
            ) : (
              egoNodes.map((node) => {
                const isCenter = node.id === conceptName;
                return (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => {
                      if (!isCenter && onSelectConcept) {
                        startTransition(() => onSelectConcept(node.id));
                      }
                    }}
                    className={cn(
                      'px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 border',
                      isCenter
                        ? 'bg-primary text-primary-foreground border-primary shadow-sm font-semibold scale-105'
                        : 'bg-card text-foreground border-border/70 hover:border-primary/50 hover:bg-muted/50 cursor-pointer',
                    )}
                  >
                    <span
                      className={cn('w-2 h-2 rounded-full', isCenter ? 'bg-primary-foreground' : 'bg-primary/60')}
                    />
                    <span className="truncate max-w-[140px]">{node.name || node.id}</span>
                  </button>
                );
              })
            )}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[11px] text-muted-foreground px-1">
            <span>{t('nearbySummary', { nodes: egoNodes.length, edges: egoEdges.length })}</span>
            <span>{t('nearbyHint')}</span>
          </div>
        </div>
      )}
    </div>
  );
}
