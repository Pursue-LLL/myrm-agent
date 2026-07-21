'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, CheckCircle2, ExternalLink, XCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { scheduleMobilePairRefresh } from '@/lib/mobileRemote';
import { useBrowserTakeoverActions } from '@/hooks/useBrowserTakeoverActions';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useChatStore from '@/store/useChatStore';
import { Button } from '@/components/primitives/button';

export default function MobileTakeoverBoard({ chatId }: { chatId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useTranslations('billing.vnc');
  const tMobile = useTranslations('agent.mobileCommand');
  const [ready, setReady] = useState(false);

  const takeoverMessageId = searchParams.get('mid')?.trim() ?? '';
  const takeoverReason = searchParams.get('reason')?.trim() ?? '';
  const takeoverPageUrl = searchParams.get('page')?.trim() ?? '';
  const pairToken = searchParams.get('pair')?.trim() ?? '';

  const pending = useBrowserTakeoverStore((state) => state.pending);
  const reason = useBrowserTakeoverStore((state) => state.reason);
  const pageUrl = useBrowserTakeoverStore((state) => state.url);
  const { handleTakeoverComplete, handleTakeoverSkip } = useBrowserTakeoverActions();

  useEffect(() => {
    return scheduleMobilePairRefresh();
  }, []);

  useEffect(() => {
    useChatStore.getState().setChatId(chatId);
    if (!takeoverMessageId) {
      return;
    }
    useBrowserTakeoverStore.getState().requestTakeover({
      reason: takeoverReason || t('takeoverExtensionHint'),
      url: takeoverPageUrl,
      messageId: takeoverMessageId,
      ui_mode: 'extension',
      auto_detect_completion: false,
    });
    setReady(true);
  }, [chatId, takeoverMessageId, takeoverReason, takeoverPageUrl, t]);

  const statusBoardUrl = useMemo(() => {
    const params = new URLSearchParams();
    if (pairToken) {
      params.set('pair', pairToken);
    }
    const query = params.toString();
    return `/mobile/status/${chatId}${query ? `?${query}` : ''}`;
  }, [chatId, pairToken]);

  const effectiveReason = reason || takeoverReason || t('takeoverExtensionHint');
  const effectivePageUrl = pageUrl || takeoverPageUrl;
  const canResolve = Boolean(ready && takeoverMessageId && pending);

  return (
    <main className="min-h-dvh bg-gradient-to-b from-background via-background to-muted/30 text-foreground">
      <div className="mx-auto flex w-full max-w-lg flex-col gap-5 px-4 py-6 sm:px-6">
        <header className="flex items-start gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push(statusBoardUrl)} className="shrink-0">
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div className="space-y-1">
            <h1 className="text-xl font-semibold tracking-tight">{t('takeoverExtensionTitle')}</h1>
            <p className="text-sm text-muted-foreground">{t('takeoverExtensionHint')}</p>
          </div>
        </header>

        <section className="rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm backdrop-blur">
          <p className="text-sm leading-relaxed text-foreground/90">{effectiveReason}</p>
          {effectivePageUrl ? (
            <a
              href={effectivePageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex max-w-full items-center gap-1 text-xs text-primary hover:underline"
            >
              <ExternalLink className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{effectivePageUrl}</span>
            </a>
          ) : null}
        </section>

        {!takeoverMessageId ? (
          <section className="rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {t('takeoverResumeFailed')}
          </section>
        ) : null}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => void handleTakeoverSkip()}
            disabled={!canResolve}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-border bg-background/70 text-sm font-medium text-muted-foreground transition-colors hover:bg-background disabled:cursor-not-allowed disabled:opacity-60"
          >
            <XCircle className="h-4 w-4" />
            {t('takeoverSkip')}
          </button>
          <button
            type="button"
            onClick={() => void handleTakeoverComplete()}
            disabled={!canResolve}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-primary text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <CheckCircle2 className="h-4 w-4" />
            {t('takeoverDone')}
          </button>
        </div>

        {!pending && takeoverMessageId ? (
          <section className="rounded-2xl border border-primary/30 bg-primary/10 px-4 py-3 text-sm text-primary">
            {t('takeoverDone')}
          </section>
        ) : null}

        <Button variant="outline" className="h-11 rounded-xl" onClick={() => router.push(statusBoardUrl)}>
          {tMobile('viewFull')}
        </Button>
      </div>
    </main>
  );
}
