'use client';

/**
 * [INPUT]
 * @/services/memory/conversationLineageDefense::HydratedHitDTO
 *
 * [OUTPUT]
 * ConversationLineageDedupView: Subview rendering lineage root families, generational
 * representatives, and collapsed ancestor/sibling slices to eliminate BM25 recall redundancy.
 *
 * [POS]
 * Subcomponent for Item 97 (LineageDedupRecallBlindnessDefenseAndAutomationDemotionSuite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { GitFork, Layers, ChevronDown, ChevronRight, User, Clock, Bot, ShieldCheck } from 'lucide-react';
import type { HydratedHitDTO } from '@/services/memory/conversationLineageDefense';

interface ConversationLineageDedupViewProps {
  hits: HydratedHitDTO[];
}

export function ConversationLineageDedupView({
  hits,
}: ConversationLineageDedupViewProps): React.JSX.Element {
  const [expandedRoots, setExpandedRoots] = useState<Record<string, boolean>>({});

  const toggleRoot = (rootId: string) => {
    setExpandedRoots((prev) => ({
      ...prev,
      [rootId]: !prev[rootId],
    }));
  };

  const getSourceIcon = (source: string) => {
    switch (source) {
      case 'interactive':
        return <User className="w-3.5 h-3.5 text-blue-500" />;
      case 'cron':
        return <Clock className="w-3.5 h-3.5 text-amber-500" />;
      default:
        return <Bot className="w-3.5 h-3.5 text-purple-500" />;
    }
  };

  const getSourceBadge = (source: string) => {
    switch (source) {
      case 'interactive':
        return (
          <Badge variant="default" className="text-[10px] font-mono uppercase bg-blue-600">
            Interactive
          </Badge>
        );
      case 'cron':
        return (
          <Badge variant="outline" className="text-[10px] font-mono uppercase text-amber-600 border-amber-500/40">
            Cron (Demoted)
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="text-[10px] font-mono uppercase text-purple-600 border-purple-500/40">
            Internal Worker
          </Badge>
        );
    }
  };

  return (
    <div className="space-y-3.5" data-testid="conversation-lineage-dedup-view">
      <div className="rounded-lg border border-border/60 bg-accent/15 p-3 text-xs space-y-1">
        <div className="flex items-center justify-between font-semibold text-foreground">
          <span className="flex items-center gap-1.5">
            <GitFork className="w-4 h-4 text-primary" />
            会话血统代际去重机制 (Generational Lineage Deduplication)
          </span>
          <span className="text-muted-foreground text-[11px] font-mono">
            {hits.length} 个独立血统根
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          当长程任务经历多轮上下文压缩（Compaction）或分支分叉时，去重引擎按 <code className="text-primary font-mono">lineage_root_id</code> 聚合历史演化切片，仅保留最新最完备代际节点，消除同一任务在检索中的重复霸榜。
        </p>
      </div>

      <div className="space-y-2.5">
        {hits.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/70 p-8 text-center text-xs text-muted-foreground">
            暂无血统会话记录，请在控制台触发检索。
          </div>
        ) : (
          hits.map((hit) => {
            const isExpanded = !!expandedRoots[hit.lineage_root_id];
            const hasCollapsed = hit.collapsed_generations_count > 0;

            return (
              <div
                key={hit.session_id}
                className="rounded-lg border border-border/60 bg-background/60 p-3 space-y-2 text-xs transition-colors hover:border-border"
                data-testid={`lineage-card-${hit.session_id}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <div className="rounded-md bg-accent/50 p-1.5">
                      {getSourceIcon(hit.source_kind)}
                    </div>
                    <div>
                      <div className="font-semibold text-foreground text-sm flex items-center gap-2">
                        <span>{hit.title}</span>
                        {hit.is_lineage_primary && (
                          <Badge variant="outline" className="text-[9px] text-emerald-600 border-emerald-500/40 flex items-center gap-0.5">
                            <ShieldCheck className="w-2.5 h-2.5" />
                            最新代表代际
                          </Badge>
                        )}
                      </div>
                      <div className="text-[11px] text-muted-foreground font-mono mt-0.5 flex items-center gap-2">
                        <span>Session: {hit.session_id}</span>
                        <span>•</span>
                        <span>Root: {hit.lineage_root_id}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5">
                    {getSourceBadge(hit.source_kind)}
                    {hasCollapsed && (
                      <Badge variant="secondary" className="text-[10px] font-mono">
                        折叠 {hit.collapsed_generations_count} 个祖先代际
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="rounded border border-border/40 bg-accent/10 p-2.5 text-[11px] text-foreground leading-relaxed font-mono">
                  {hit.content_snippet}
                </div>

                {hasCollapsed && (
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => toggleRoot(hit.lineage_root_id)}
                      aria-label={`${isExpanded ? '收起' : '展开'}折叠的 ${hit.collapsed_generations_count} 个历史代际`}
                      className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline focus:outline-none focus:ring-2 focus:ring-primary rounded px-1 py-0.5"
                      data-testid={`btn-toggle-collapsed-${hit.session_id}`}
                    >
                      {isExpanded ? (
                        <>
                          <ChevronDown className="w-3.5 h-3.5" />
                          收起折叠代际 ({hit.collapsed_generations_count})
                        </>
                      ) : (
                        <>
                          <ChevronRight className="w-3.5 h-3.5" />
                          展开折叠的 {hit.collapsed_generations_count} 个历史代际切片
                        </>
                      )}
                    </button>

                    {isExpanded && (
                      <div
                        className="mt-2 rounded border border-border/50 bg-background/80 p-2.5 space-y-1.5 text-[11px]"
                        data-testid={`collapsed-panel-${hit.session_id}`}
                      >
                        <div className="text-muted-foreground font-medium flex items-center gap-1">
                          <Layers className="w-3 h-3 text-muted-foreground" />
                          已合并至当前代表节点的历史会话世代：
                        </div>
                        <ul className="list-disc list-inside space-y-1 text-muted-foreground font-mono text-[10px]">
                          {hit.collapsed_session_ids.map((id) => (
                            <li key={id} className="text-foreground">
                              {id} <span className="text-muted-foreground">(历史压缩切片已折叠)</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
