'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { wikiService, type WikiGraphInsights } from '@/services/wikiService';

interface WikiGraphInsightsPanelProps {
  agentId?: string | null;
}

function insightLabel(record: Record<string, unknown>): string {
  const candidates = ['label', 'name', 'topic', 'concept', 'source', 'target', 'description'];
  for (const key of candidates) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return JSON.stringify(record).slice(0, 120);
}

export default function WikiGraphInsightsPanel({ agentId }: WikiGraphInsightsPanelProps) {
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
        <div className="space-y-4 text-sm">
          <section>
            <h4 className="font-medium text-foreground">{t('gapsTitle', { count: insights.knowledge_gaps.length })}</h4>
            {insights.knowledge_gaps.length === 0 ? (
              <p className="mt-1 text-xs text-muted-foreground">{t('emptyGaps')}</p>
            ) : (
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {insights.knowledge_gaps.slice(0, 5).map((item, index) => (
                  <li key={`gap-${index}`} className="truncate">
                    {insightLabel(item)}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section>
            <h4 className="font-medium text-foreground">
              {t('connectionsTitle', { count: insights.unexpected_connections.length })}
            </h4>
            {insights.unexpected_connections.length === 0 ? (
              <p className="mt-1 text-xs text-muted-foreground">{t('emptyConnections')}</p>
            ) : (
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {insights.unexpected_connections.slice(0, 5).map((item, index) => (
                  <li key={`conn-${index}`} className="truncate">
                    {insightLabel(item)}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section>
            <h4 className="font-medium text-foreground">
              {t('communitiesTitle', { count: insights.communities.length })}
            </h4>
            {insights.communities.length === 0 ? (
              <p className="mt-1 text-xs text-muted-foreground">{t('emptyCommunities')}</p>
            ) : (
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {insights.communities.slice(0, 5).map((item, index) => (
                  <li key={`community-${index}`} className="truncate">
                    {insightLabel(item)}
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
