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
import { cn } from '@/lib/utils/classnameUtils';

/** Hub plus the members shown as chips under it. */
const MAX_VISIBLE_MEMBERS = 5;

interface NodeLinkProps {
  nodeId: string;
  onSelect?: (nodeId: string) => void;
  className?: string;
}

/** The label the graph viewer draws on a page's node. */
const pageLabel = (nodeId: string) => nodeId.replace(/-/g, ' ');

/** Page name that focuses the page in the graph when a handler is provided. */
function NodeLink({ nodeId, onSelect, className }: NodeLinkProps) {
  const label = pageLabel(nodeId);
  if (!onSelect) {
    return (
      <span className={className} title={label}>
        {label}
      </span>
    );
  }
  return (
    <button
      type="button"
      title={label}
      onClick={() => onSelect(nodeId)}
      className={cn(
        'cursor-pointer text-left transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className,
      )}
    >
      {label}
    </button>
  );
}

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
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => void loadInsights()}
          disabled={loading}
          aria-label={t('refresh')}
          title={t('refresh')}
        >
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
                        <span className="truncate text-xs font-medium text-foreground">{pageLabel(item.node)}</span>
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
                {insights.unexpected_connections
                  .slice(0, 6)
                  .map((item: WikiUnexpectedConnectionItem, index: number) => (
                    <li
                      key={`conn-${index}`}
                      className="flex items-center justify-between gap-2 rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1.5 transition-colors hover:bg-muted/60"
                    >
                      <div className="min-w-0 flex-1 truncate text-xs">
                        <NodeLink
                          nodeId={item.source}
                          onSelect={onSelectNode}
                          className="font-medium text-foreground"
                        />
                        <span className="mx-1 text-muted-foreground">↔</span>
                        <NodeLink
                          nodeId={item.target}
                          onSelect={onSelectNode}
                          className="font-medium text-foreground"
                        />
                      </div>
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
                {insights.communities.slice(0, 5).map((item: WikiCommunityItem) => {
                  // Members arrive hub-first: the best-connected page names the cluster.
                  const [hub, ...others] = item.members.slice(0, MAX_VISIBLE_MEMBERS);
                  const hiddenCount = item.size - 1 - others.length;
                  const cohesionPercent = Math.round(item.cohesion * 100);
                  return (
                    <li
                      key={`community-${item.id}`}
                      className="space-y-1.5 rounded-lg border border-border/40 bg-muted/30 p-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <NodeLink
                          nodeId={hub}
                          onSelect={onSelectNode}
                          className="min-w-0 truncate font-medium text-foreground"
                        />
                        <span className="shrink-0 text-[10px] text-muted-foreground">
                          {t('communitySize', { count: item.size })} · {t('cohesion')} {cohesionPercent}%
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {others.map((member) => (
                          <NodeLink
                            key={member}
                            nodeId={member}
                            onSelect={onSelectNode}
                            className="max-w-full truncate rounded bg-background/80 px-1.5 py-0.5 text-[10px] text-foreground"
                          />
                        ))}
                        {hiddenCount > 0 ? (
                          <span className="text-[10px] text-muted-foreground">+{hiddenCount}</span>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      ) : null}
    </aside>
  );
}
