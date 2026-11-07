'use client';

/**
 * [INPUT] ./useWikiQuery::WikiQueryController (POS: 问答的输入、结果与抽屉状态), @/components/features/message-box/SourceChunkDrawer (POS: 证据片段抽屉)
 * [OUTPUT] WikiQueryCard: “问答”卡: 检索模式选择 (自动 / 原始 claim)、问题输入 (回车提交)、提交按钮、问答结果与证据片段抽屉
 * [POS] 总览页的问答卡; 问题为空时不可提交, 提交中禁用按钮。
 */

import { useTranslations } from 'next-intl';
import { IconBook } from '@/components/features/icons/PremiumIcons';
import SourceChunkDrawer from '@/components/features/message-box/SourceChunkDrawer';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import type { WikiQueryController } from './useWikiQuery';
import { WikiQueryResults } from './WikiQueryResults';

interface WikiQueryCardProps {
  wikiQuery: WikiQueryController;
  agentScopeId: string | null;
  evidenceContextKey: string;
}

export function WikiQueryCard({ wikiQuery, agentScopeId, evidenceContextKey }: WikiQueryCardProps) {
  const t = useTranslations('settings.wiki');
  const {
    query,
    setQuery,
    queryMode,
    setQueryMode,
    handleQuery,
    isQuerying,
    snippetDrawerState,
    setSnippetDrawerState,
  } = wikiQuery;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconBook className="w-5 h-5" />
            {t('query.title')}
          </CardTitle>
          <CardDescription>{t('query.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
            <div className="flex w-full flex-col gap-1.5 lg:w-56">
              <label htmlFor="wiki-query-mode" className="text-xs font-medium text-muted-foreground">
                {t('query.modeLabel')}
              </label>
              <Select value={queryMode} onValueChange={(value) => setQueryMode(value as 'auto' | 'raw_claim')}>
                <SelectTrigger id="wiki-query-mode" className="w-full">
                  <SelectValue placeholder={t('query.modeAuto')}>
                    {queryMode === 'raw_claim' ? t('query.modeRawClaim') : t('query.modeAuto')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">{t('query.modeAuto')}</SelectItem>
                  <SelectItem value="raw_claim">{t('query.modeRawClaim')}</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {queryMode === 'raw_claim' ? t('query.modeRawClaimHint') : t('query.modeAutoHint')}
              </p>
            </div>
            <div className="flex w-full flex-1 flex-col gap-2 sm:flex-row">
              <Input
                placeholder={t('query.placeholder')}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
                className="flex-1"
              />
              <Button onClick={handleQuery} disabled={isQuerying || !query.trim()} className="w-full sm:w-auto">
                {isQuerying ? t('querying') : t('actions.query')}
              </Button>
            </div>
          </div>
          <WikiQueryResults wikiQuery={wikiQuery} agentScopeId={agentScopeId} />
        </CardContent>
      </Card>
      <SourceChunkDrawer
        open={snippetDrawerState.open}
        onOpenChange={(open) => setSnippetDrawerState((prev) => ({ ...prev, open }))}
        title={snippetDrawerState.title}
        section={snippetDrawerState.section}
        snippet={snippetDrawerState.snippet}
        level={snippetDrawerState.level}
        snapshotStatus={snippetDrawerState.snapshotStatus}
        claimStatus={snippetDrawerState.claimStatus}
        claimConfidence={snippetDrawerState.claimConfidence}
        claimText={snippetDrawerState.claimText}
        resourceUri={snippetDrawerState.resourceUri}
        supersededFromUri={snippetDrawerState.supersededFromUri}
        thumbnailUrl={snippetDrawerState.thumbnailUrl}
        surface="settings"
        contextKey={evidenceContextKey}
      />
    </>
  );
}
