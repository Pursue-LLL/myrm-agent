'use client';

/**
 * [INPUT] ./useWikiQuery::WikiQueryController (POS: 问答结果与抽屉状态), @/lib/wiki/claimStatusDisplay::formatClaimConfidence (POS: 置信度展示)
 * [OUTPUT] WikiQueryResults: 问答结果: 拒答标签或置信度、回答正文 (拒答时用 destructive 色块)、检索轨迹、证据片段与相关文章; 没有回答时不渲染
 * [POS] 问答卡里提交之后出现的区域; 拒答标签文字使用 text-destructive-text。
 */

import { useLocale, useTranslations } from 'next-intl';
import { formatClaimConfidence } from '@/lib/wiki/claimStatusDisplay';
import type { WikiQueryController } from './useWikiQuery';
import { WikiRetrievalTracePanel } from './WikiRetrievalTracePanel';
import { WikiSourceSnippetList } from './WikiSourceSnippetList';

interface WikiQueryResultsProps {
  wikiQuery: Pick<
    WikiQueryController,
    | 'answer'
    | 'queryRefused'
    | 'queryConfidence'
    | 'retrievalTrace'
    | 'sourceSnippets'
    | 'relatedArticles'
    | 'setSnippetDrawerState'
  >;
  agentScopeId: string | null;
}

export function WikiQueryResults({ wikiQuery, agentScopeId }: WikiQueryResultsProps) {
  const t = useTranslations('settings.wiki');
  const locale = useLocale();
  const {
    answer,
    queryRefused,
    queryConfidence,
    retrievalTrace,
    sourceSnippets,
    relatedArticles,
    setSnippetDrawerState,
  } = wikiQuery;

  if (!answer) {
    return null;
  }

  return (
    <div className="space-y-2">
      {queryRefused ? (
        <div className="text-xs font-medium text-destructive-text">{t('query.refusedLabel')}</div>
      ) : (
        queryConfidence !== null && (
          <div className="text-xs text-muted-foreground">
            {t('query.confidenceScore', {
              value: formatClaimConfidence(queryConfidence, locale),
            })}
          </div>
        )
      )}
      <div className="text-sm font-medium">{t('query.answer')}</div>
      <div
        className={
          queryRefused
            ? 'p-4 rounded-lg whitespace-pre-wrap border border-destructive/40 bg-destructive/5'
            : 'p-4 bg-muted rounded-lg whitespace-pre-wrap'
        }
      >
        {answer}
      </div>

      <WikiRetrievalTracePanel retrievalTrace={retrievalTrace} />

      <WikiSourceSnippetList
        sourceSnippets={sourceSnippets}
        agentScopeId={agentScopeId}
        onOpenSnippet={setSnippetDrawerState}
      />

      {relatedArticles.length > 0 && (
        <div className="mt-4">
          <div className="text-sm font-medium mb-2">{t('query.relatedArticles')}</div>
          <div className="flex flex-wrap gap-2">
            {relatedArticles.map((article, idx) => (
              <span key={idx} className="px-2 py-1 bg-primary/10 text-primary rounded text-sm">
                {article}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
