'use client';

/**
 * [INPUT]
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

import { useEffect, useState, useTransition } from 'react';
import { ArrowUpRight, CornerDownLeft, Network, FileText, AlertCircle, RefreshCw } from 'lucide-react';
import { wikiService, type ConceptLinksResponse, type ConceptLinkItem } from '@/services/wikiService';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';

interface WikiConceptLinksPanelProps {
  conceptName: string;
  agentId?: string | null;
  onSelectConcept?: (name: string) => void;
}

export function WikiConceptLinksPanel({
  conceptName,
  agentId,
  onSelectConcept,
}: WikiConceptLinksPanelProps) {
  const [linksData, setLinksData] = useState<ConceptLinksResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'backlinks' | 'outlinks' | 'ego'>('backlinks');
  const [, startTransition] = useTransition();

  const fetchLinks = async () => {
    if (!conceptName) return;
    setLoading(true);
    setError(null);
    try {
      const data = await wikiService.getConceptLinks(conceptName, 1, agentId);
      setLinksData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load concept links');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLinks();
  }, [conceptName, agentId]);

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

  return (
    <div id="wiki-concept-links" className="rounded-xl border border-border/70 bg-card/60 backdrop-blur-sm p-4 space-y-4 shadow-sm">
      {/* 头部导航与统计胶囊 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-3">
        <div className="flex items-center gap-2">
          <Network className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold tracking-tight text-foreground">
            双向链接与知识脉络
          </span>
          <span className="text-[11px] px-2 py-0.5 rounded-full font-mono bg-primary/10 text-primary border border-primary/20">
            {backlinks.length} 引用 · {outlinks.length} 出链
          </span>
        </div>

        {/* 视图切换按钮组 */}
        <div className="flex items-center gap-1 bg-muted/40 p-0.5 rounded-lg border border-border/40 text-xs">
          <button
            type="button"
            onClick={() => setActiveTab('backlinks')}
            className={cn(
              'px-2.5 py-1 rounded-md transition-all font-medium flex items-center gap-1.5',
              activeTab === 'backlinks'
                ? 'bg-background text-foreground shadow-xs border border-border/60'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <CornerDownLeft className="w-3.5 h-3.5 text-sky-500" />
            <span>被引脉络 ({backlinks.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('outlinks')}
            className={cn(
              'px-2.5 py-1 rounded-md transition-all font-medium flex items-center gap-1.5',
              activeTab === 'outlinks'
                ? 'bg-background text-foreground shadow-xs border border-border/60'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <ArrowUpRight className="w-3.5 h-3.5 text-emerald-500" />
            <span>引用前置 ({outlinks.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('ego')}
            className={cn(
              'px-2.5 py-1 rounded-md transition-all font-medium flex items-center gap-1.5',
              activeTab === 'ego'
                ? 'bg-background text-foreground shadow-xs border border-border/60'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <Network className="w-3.5 h-3.5 text-indigo-500" />
            <span>局部拓扑 ({egoNodes.length})</span>
          </button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={fetchLinks}
            className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
            title="刷新链接拓扑"
          >
            <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {error && (
        <div className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/20 p-2.5 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Tab 1: 反向链接（Backlinks） */}
      {activeTab === 'backlinks' && (
        <div className="space-y-2">
          {backlinks.length === 0 ? (
            <p className="text-xs text-muted-foreground py-3 text-center">
              暂无上游词条或研报直接引用此知识点
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-2">
              {backlinks.map((link: ConceptLinkItem) => (
                <div
                  key={link.name}
                  onClick={() => {
                    if (link.exists && onSelectConcept) {
                      startTransition(() => onSelectConcept(link.name));
                    }
                  }}
                  className={cn(
                    'group rounded-lg border p-2.5 transition-all text-left flex flex-col gap-1',
                    link.exists
                      ? 'border-border/60 bg-muted/15 hover:bg-muted/30 hover:border-primary/40 cursor-pointer'
                      : 'border-dashed border-amber-500/30 bg-amber-500/5 cursor-default'
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 font-medium text-xs text-foreground group-hover:text-primary transition-colors">
                      <FileText className="w-3.5 h-3.5 text-sky-500 shrink-0" />
                      <span className="truncate">{link.name}</span>
                      {!link.exists && (
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                          待补充
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      权重 {link.weight.toFixed(1)}
                    </span>
                  </div>

                  {link.context_snippet && (
                    <p className="text-[11px] text-muted-foreground bg-background/50 border border-border/40 rounded px-2 py-1 leading-relaxed font-mono line-clamp-2">
                      &ldquo;{link.context_snippet}&rdquo;
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: 引用前置（Outlinks） */}
      {activeTab === 'outlinks' && (
        <div className="space-y-2">
          {outlinks.length === 0 ? (
            <p className="text-xs text-muted-foreground py-3 text-center">
              此词条尚未显式引用其他知识点
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {outlinks.map((link: ConceptLinkItem) => (
                <div
                  key={link.name}
                  onClick={() => {
                    if (link.exists && onSelectConcept) {
                      startTransition(() => onSelectConcept(link.name));
                    }
                  }}
                  className={cn(
                    'group rounded-lg border p-2.5 transition-all text-left flex items-center justify-between gap-2',
                    link.exists
                      ? 'border-border/60 bg-muted/15 hover:bg-muted/30 hover:border-emerald-500/40 cursor-pointer'
                      : 'border-dashed border-amber-500/30 bg-amber-500/5 cursor-default'
                  )}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <ArrowUpRight className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                    <span className="text-xs font-medium text-foreground truncate group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                      {link.name}
                    </span>
                  </div>
                  {!link.exists ? (
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 shrink-0">
                      幽灵引用
                    </span>
                  ) : (
                    <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                      W{link.weight.toFixed(1)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 3: 局部拓扑微型雷达（Ego Graph） */}
      {activeTab === 'ego' && (
        <div className="space-y-3">
          <div className="rounded-lg border border-border/60 bg-muted/20 p-3 min-h-[120px] flex flex-wrap items-center justify-center gap-2">
            {egoNodes.length === 0 ? (
              <p className="text-xs text-muted-foreground">暂无局部拓扑数据</p>
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
                        : 'bg-card text-foreground border-border/70 hover:border-primary/50 hover:bg-muted/50 cursor-pointer'
                    )}
                  >
                    <span
                      className={cn(
                        'w-2 h-2 rounded-full',
                        isCenter ? 'bg-primary-foreground' : 'bg-primary/60'
                      )}
                    />
                    <span className="truncate max-w-[140px]">{node.name || node.id}</span>
                  </button>
                );
              })
            )}
          </div>
          <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
            <span>局部关联网：{egoNodes.length} 节点 · {egoEdges.length} 关系边</span>
            <span>点击节点可立即穿透阅读</span>
          </div>
        </div>
      )}
    </div>
  );
}
