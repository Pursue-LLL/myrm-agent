/**
 * [INPUT] @/services/wikiService::wikiService (POS: Wiki 问答接口), @/services/wiki/evidenceMetrics (POS: 证据展示埋点), @/services/riskHeldToast::isRiskHeldError (POS: 被风控规则拦下的提问已有统一提示)
 * [OUTPUT] useWikiQuery: 总览页问答的输入 (问题、检索模式)、结果 (回答、置信度、是否拒答、检索轨迹、证据片段、相关文章)、证据抽屉状态与提交动作
 * [POS] 总览页“问答”卡的数据层: 切换范围时清空上一次的回答、片段与相关文章; 被风控拦下的提问只出统一提示, 其它失败照常提示。
 */

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { isRiskHeldError } from '@/services/riskHeldToast';
import {
  recordEvidenceSurface,
  recordWikiQueryAttempt,
  recordWikiQuerySubmitted,
} from '@/services/wiki/evidenceMetrics';
import { wikiService, type WikiRetrievalTrace, type WikiSourceSnippet } from '@/services/wikiService';
import type { WikiSnippetDrawerState } from './types';

export function useWikiQuery(agentScopeId: string | null, evidenceContextKey: string) {
  const t = useTranslations('settings.wiki');
  const [query, setQuery] = useState('');
  const [queryMode, setQueryMode] = useState<'auto' | 'raw_claim'>('auto');
  const [answer, setAnswer] = useState('');
  const [relatedArticles, setRelatedArticles] = useState<string[]>([]);
  const [sourceSnippets, setSourceSnippets] = useState<WikiSourceSnippet[]>([]);
  const [queryConfidence, setQueryConfidence] = useState<number | null>(null);
  const [queryRefused, setQueryRefused] = useState<boolean>(false);
  const [retrievalTrace, setRetrievalTrace] = useState<WikiRetrievalTrace | null>(null);
  const [snippetDrawerState, setSnippetDrawerState] = useState<WikiSnippetDrawerState>({
    open: false,
    title: '',
    snippet: '',
  });
  const [isQuerying, setIsQuerying] = useState(false);

  useEffect(() => {
    setAnswer('');
    setRelatedArticles([]);
    setSourceSnippets([]);
  }, [agentScopeId]);

  const handleQuery = async () => {
    if (!query.trim()) {
      toast.error(t('errors.emptyQuery'));
      return;
    }

    recordWikiQueryAttempt('settings', evidenceContextKey);
    setIsQuerying(true);
    setAnswer('');
    setRelatedArticles([]);
    setSourceSnippets([]);
    setQueryConfidence(null);
    setQueryRefused(false);
    setRetrievalTrace(null);

    try {
      const data = await wikiService.queryWiki(query, queryMode, agentScopeId);

      setAnswer(data.answer);
      setRelatedArticles(data.related_articles || []);
      setSourceSnippets(data.source_snippets || []);
      setQueryConfidence(typeof data.confidence_score === 'number' ? data.confidence_score : null);
      setQueryRefused(Boolean(data.refused));
      setRetrievalTrace(data.retrieval_trace ?? null);
      recordWikiQuerySubmitted('settings', evidenceContextKey);
      recordEvidenceSurface('settings', data.source_snippets?.length ?? 0, evidenceContextKey);
      toast.success(t('success.queryComplete'));
    } catch (error) {
      console.error('Query failed:', error);
      if (!isRiskHeldError(error)) {
        toast.error(t('errors.queryFailed'));
      }
    } finally {
      setIsQuerying(false);
    }
  };

  return {
    query,
    setQuery,
    queryMode,
    setQueryMode,
    answer,
    relatedArticles,
    sourceSnippets,
    queryConfidence,
    queryRefused,
    retrievalTrace,
    snippetDrawerState,
    setSnippetDrawerState,
    isQuerying,
    handleQuery,
  };
}

export type WikiQueryController = ReturnType<typeof useWikiQuery>;
