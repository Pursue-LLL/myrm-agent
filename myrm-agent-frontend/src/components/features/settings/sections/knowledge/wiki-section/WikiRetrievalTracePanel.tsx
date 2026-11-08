'use client';

/**
 * [INPUT] @/services/wikiService::WikiRetrievalTrace (POS: 问答的检索轨迹)
 * [OUTPUT] WikiRetrievalTracePanel: 检索轨迹面板: 索引命中、sidecar 目录、种子 (最多 6 个) 与选中的概念, 四类都为空时不渲染
 * [POS] 问答结果里解释“答案从哪些页面检索而来”的折叠信息。
 */

import { useTranslations } from 'next-intl';
import type { WikiRetrievalTrace } from '@/services/wikiService';

interface WikiRetrievalTracePanelProps {
  retrievalTrace: WikiRetrievalTrace | null;
}

export function WikiRetrievalTracePanel({ retrievalTrace }: WikiRetrievalTracePanelProps) {
  const t = useTranslations('settings.wiki');

  if (!retrievalTrace) {
    return null;
  }
  const hasDetails =
    retrievalTrace.index_hits.length > 0 ||
    retrievalTrace.seeds.length > 0 ||
    retrievalTrace.sidecar_directories.length > 0 ||
    retrievalTrace.selected_concepts.length > 0;
  if (!hasDetails) {
    return null;
  }

  return (
    <div className="mt-4 space-y-2 rounded-lg border border-border/60 bg-card/40 p-3">
      <div className="text-sm font-medium">{t('query.retrievalTraceTitle')}</div>
      {retrievalTrace.index_hits.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-muted-foreground">{t('query.retrievalTraceIndex')}</div>
          {retrievalTrace.index_hits.map((hit) => (
            <div key={hit.link_name} className="text-xs text-muted-foreground">
              [[{hit.link_name}]] — {hit.summary}
            </div>
          ))}
        </div>
      )}
      {retrievalTrace.sidecar_directories.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-muted-foreground">{t('query.retrievalTraceSidecar')}</div>
          <div className="text-xs text-muted-foreground font-mono break-all">
            {retrievalTrace.sidecar_directories.join(' · ')}
          </div>
        </div>
      )}
      {retrievalTrace.seeds.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-muted-foreground">{t('query.retrievalTraceSeeds')}</div>
          <div className="space-y-1">
            {retrievalTrace.seeds.slice(0, 6).map((seed) => (
              <div
                key={`${seed.source}-${seed.concept_name}`}
                className="text-xs text-muted-foreground font-mono break-all"
              >
                {seed.concept_name} ({seed.source})
              </div>
            ))}
          </div>
        </div>
      )}
      {retrievalTrace.selected_concepts.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-muted-foreground">{t('query.retrievalTraceConcepts')}</div>
          <div className="text-xs text-muted-foreground font-mono">{retrievalTrace.selected_concepts.join(' · ')}</div>
        </div>
      )}
    </div>
  );
}
