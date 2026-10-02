'use client';

/**
 * [INPUT]
 * fetch POST {text, title} -> /api/v1/wiki/daily-review (buildWikiApiPath)
 * useTranslations('settings.wiki') (POS: i18n locale namespace)
 *
 * [OUTPUT]
 * DailyReviewCard: one-click daily review journal card in knowledge settings.
 *
 * [POS]
 * One-click daily review entry. The review text is stored verbatim as raw
 * evidence and compiled into four-dimension knowledge drafts (Projects /
 * Knowledge / Methods / Comparisons) that await human review before publish.
 */

import Link from 'next/link';
import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { NotebookPen, Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { buildWikiApiPath } from '@/services/wikiService';

interface DailyReviewResponse {
  success: boolean;
  raw_path: string;
  enqueued: boolean;
  skipped: boolean;
  message: string;
}

export default function DailyReviewCard() {
  const t = useTranslations('settings.wiki');
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DailyReviewResponse | null>(null);

  const handleSubmit = useCallback(async () => {
    if (!text.trim()) {
      setError(t('dailyReview.empty'));
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch(buildWikiApiPath('/wiki/daily-review'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, title }),
      });
      const payload = (await response.json()) as DailyReviewResponse & { detail?: { message?: string } };
      if (!response.ok || !payload.success) {
        throw new Error(payload.detail?.message || payload.message || `HTTP ${response.status}`);
      }
      setResult(payload);
      setText('');
      setTitle('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('dailyReview.error'));
    } finally {
      setSubmitting(false);
    }
  }, [text, title, t]);

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
          {submitting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <NotebookPen className="w-4 h-4" />
          )}
          {submitting ? t('dailyReview.submitting') : t('dailyReview.submitButton')}
        </Button>

        {error && (
          <p className="text-sm text-destructive" data-testid="daily-review-error">
            {error}
          </p>
        )}

        {result && (
          <div
            className="rounded-lg border border-border/60 bg-muted/40 p-4 text-sm"
            data-testid="daily-review-result"
          >
            {result.skipped ? t('dailyReview.skipped') : t('dailyReview.staged')}
            {!result.skipped && (
              <Link
                href="/settings/knowledge?wikiTab=pendingEdits"
                className="ml-2 font-medium text-primary underline-offset-4 hover:underline"
                data-testid="daily-review-goto-pending"
              >
                {t('dailyReview.reviewCta')}
              </Link>
            )}
            <p className="mt-1 text-xs text-muted-foreground">{result.raw_path}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
