'use client';

/**
 * [INPUT]
 * - ./WikiAgentScopeContext::useWikiAgentScope (POS: agent vault the review is stored into)
 * - @/lib/api::apiRequest, ApiError (POS: unified frontend API request entry; ApiError.businessCode carries the server's error code)
 * - @/services/wikiService::buildWikiApiPath (POS: Wiki endpoint path builder with optional agent_id query)
 * - POST {text, title} to /wiki/daily-review
 * - useTranslations('settings.wiki') (POS: i18n locale namespace)
 *
 * [OUTPUT]
 * DailyReviewCard: one-click daily review journal card in knowledge settings.
 *
 * [POS]
 * One-click daily review entry. The review text is stored verbatim as raw
 * evidence in the selected agent's vault and compiled into four-dimension knowledge
 * drafts (Projects / Knowledge / Methods / Comparisons) that await human review before
 * publish. Failures show the localized message only: the server's reasons are English
 * diagnostics, not user copy. A security block is the one failure that names its cause: the
 * text holds credentials, so only editing the text, which is kept, can make a retry succeed.
 */

import Link from 'next/link';
import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { NotebookPen, Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { ApiError, apiRequest } from '@/lib/api';
import { buildWikiApiPath } from '@/services/wikiService';
import { useWikiAgentScope } from './WikiAgentScopeContext';

interface DailyReviewResult {
  skipped: boolean;
  /** Vault the review went into: the pending-review link must open it even after the scope switches. */
  agentScopeId: string | null;
}

function pendingEditsHref(agentScopeId: string | null): string {
  const params = new URLSearchParams({ wikiTab: 'pendingEdits' });
  if (agentScopeId) {
    params.set('agentId', agentScopeId);
  }
  return `/settings/wiki?${params.toString()}`;
}

export default function DailyReviewCard() {
  const t = useTranslations('settings.wiki');
  const { agentScopeId } = useWikiAgentScope();
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DailyReviewResult | null>(null);

  const handleSubmit = useCallback(async () => {
    if (!text.trim()) {
      setError(t('dailyReview.empty'));
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      // silent: the error is shown inline under the form, not as a global toast.
      const { skipped } = await apiRequest<{ skipped: boolean }>(buildWikiApiPath('/wiki/daily-review', agentScopeId), {
        method: 'POST',
        body: JSON.stringify({ text, title }),
        silent: true,
      });
      setResult({ skipped, agentScopeId });
      setText('');
      setTitle('');
    } catch (err) {
      setError(
        err instanceof ApiError && err.businessCode === 'security_blocked'
          ? t('dailyReview.securityBlocked')
          : t('dailyReview.error'),
      );
    } finally {
      setSubmitting(false);
    }
  }, [text, title, agentScopeId, t]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <NotebookPen className="w-5 h-5" />
          {t('dailyReview.title')}
        </CardTitle>
        <CardDescription>{t('dailyReview.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t('dailyReview.titleLabel')}
          maxLength={120}
          className="sm:max-w-[240px]"
          data-testid="daily-review-title-input"
        />
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('dailyReview.placeholder')}
          rows={6}
          className="min-h-[120px] resize-y"
          data-testid="daily-review-text-input"
        />
        <Button
          onClick={handleSubmit}
          disabled={submitting}
          className="w-full sm:w-auto"
          data-testid="daily-review-submit-btn"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <NotebookPen className="w-4 h-4" />}
          {submitting ? t('dailyReview.submitting') : t('dailyReview.submitButton')}
        </Button>

        {error && (
          <p className="text-sm text-destructive-text" data-testid="daily-review-error">
            {error}
          </p>
        )}

        {result && (
          <div className="rounded-lg border border-border/60 bg-muted/40 p-4 text-sm" data-testid="daily-review-result">
            {result.skipped ? t('dailyReview.skipped') : t('dailyReview.staged')}
            {!result.skipped && (
              <Link
                href={pendingEditsHref(result.agentScopeId)}
                className="ml-2 font-medium text-primary underline-offset-4 hover:underline"
                data-testid="daily-review-goto-pending"
              >
                {t('dailyReview.reviewCta')}
              </Link>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
