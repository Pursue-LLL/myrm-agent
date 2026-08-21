'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, RefreshCw, Focus, GitFork, Network, Layers } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import {
  wikiService,
  type WikiGraphInsights,
  type WikiKnowledgeGapItem,
  type WikiUnexpectedConnectionItem,
  type WikiCommunityItem,
} from '@/services/wikiService';

interface WikiGraphInsightsPanelProps {
  agentId?: string | null;
  onSelectNode?: (nodeId: string) => void;
}

export default function WikiGraphInsightsPanel({ agentId, onSelectNode }: WikiGraphInsightsPanelProps) {
  const t = useTranslations('library.graph.insights');
  const [insights, setInsights] = useState<WikiGraphInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadInsights = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const data = await wikiService.getGraphInsights(agentId);
      setInsights(data);
    } catch (loadError) {
      console.error('Failed to load graph insights:', loadError);
      setError(true);
      setInsights(null);
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    void loadInsights();
  }, [loadInsights]);

  return (
    <aside
      className="w-full shrink-0 space-y-4 rounded-xl border border-border/60 bg-card/60 p-4 lg:w-80"
      data-testid="wiki-graph-insights-panel"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
        <Button type="button" variant="ghost" size="icon" onClick={() => void loadInsights()} disabled={loading}>
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t('description')}</p>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('loading')}
        </div>
      ) : null}

      {!loading && error ? (
        <div className="space-y-2">
          <p className="text-sm text-rose-700 dark:text-rose-300">{t('error')}</p>
          <Button type="button" variant="outline" size="sm" onClick={() => void loadInsights()}>
            {t('retry')}
          </Button>
        </div>
      ) : null}

      {!loading && !error && insights ? (
        <div className="space-y-5 text-sm">
          {/* Knowledge Gaps */}
          <section className="space-y-2">
            <div className="flex items-center gap-1.5 font-medium text-foreground">
              <Network className="h-4 w-4 text-amber-500" />
              <h4>{t('gapsTitle', { count: insights.knowledge_gaps.length })}</h4>
            </div>
            {insights.knowledge_gaps.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('emptyGaps')}</p>
            ) : (
              <ul className="space-y-1.5">
                {insights.knowledge_gaps.slice(0, 6).map((item: WikiKnowledgeGapItem, index: number) => (
                  <li
                    key={`gap-${index}`}
                    className="flex items-center justify-between gap-2 rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1.5 transition-colors hover:bg-muted/60"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-xs font-medium text-foreground">{item.node}</span>
                        <span
                          className={`rounded px-1.5 py-0.2 text-[10px] font-medium ${
                            item.type === 'isolated'
                              ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                              : 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400'
                          }`}
                        >
                          {item.type === 'isolated' ? t('isolated') : t('bridge')}
                        </span>
                      </div>
                    </div>
                    {onSelectNode ? (
                      <button
                        type="button"
                        onClick={() => onSelectNode(item.node)}
                        className="flex shrink-0 items-center gap-1 rounded p-1 text-[10px] text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
                        title={t('locate')}
                      >
                        <Focus className="h-3 w-3" />
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Unexpected Connections */}
          <section className="space-y-2">
            <div className="flex items-center gap-1.5 font-medium text-foreground">
              <GitFork className="h-4 w-4 text-emerald-500" />
              <h4>{t('connectionsTitle', { count: insights.unexpected_connections.length })}</h4>
            </div>
            {insights.unexpected_connections.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('emptyConnections')}</p>
            ) : (
              <ul className="space-y-1.5">
                {insights.unexpected_connections.slice(0, 6).map((item: WikiUnexpectedConnectionItem, index: number) => (
                  <li
                    key={`conn-${index}`}
                    className="flex items-center justify-between gap-2 rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1.5 transition-colors hover:bg-muted/60"
                  >
                    <div className="min-w-0 flex-1 truncate text-xs">
                      <span
                        className="cursor-pointer font-medium text-foreground hover:underline"
                        onClick={() => onSelectNode?.(item.source)}
                      >
                        {item.source}
                      </span>
                      <span className="mx-1 text-muted-foreground">↔</span>
                      <span
                        className="cursor-pointer font-medium text-foreground hover:underline"
                        onClick={() => onSelectNode?.(item.target)}
                      >
                        {item.target}
                      </span>
                    </div>
                    <span className="shrink-0 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                      w={item.weight}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Communities */}
          <section className="space-y-2">
            <div className="flex items-center gap-1.5 font-medium text-foreground">
              <Layers className="h-4 w-4 text-sky-500" />
              <h4>{t('communitiesTitle', { count: insights.communities.length })}</h4>
            </div>
            {insights.communities.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('emptyCommunities')}</p>
            ) : (
              <ul className="space-y-1.5">
                {insights.communities.slice(0, 5).map((item: WikiCommunityItem, index: number) => (
                  <li
                    key={`community-${index}`}
                    className="space-y-1 rounded-lg border border-border/40 bg-muted/30 p-2 text-xs"
                  >
                    <div className="flex items-center justify-between text-muted-foreground">
                      <span className="font-medium text-foreground">
                        Cluster #{item.id} ({item.size} {t('members')})
                      </span>
                      <span className="text-[10px]">
                        {t('cohesion')}: {Math.round(item.cohesion * 100)}%
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {item.members.slice(0, 4).map((member, mIdx) => (
                        <span
                          key={mIdx}
                          onClick={() => onSelectNode?.(member)}
                          className="cursor-pointer rounded bg-background/80 px-1.5 py-0.5 text-[10px] text-foreground transition-colors hover:bg-primary/20"
                        >
                          {member}
                        </span>
                      ))}
                      {item.members.length > 4 ? (
                        <span className="text-[10px] text-muted-foreground">+{item.members.length - 4}</span>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      ) : null}
    </aside>
  );
}
