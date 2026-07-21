'use client';

/**
 * [INPUT]
 * - useBrowserTakeoverStore (POS: 浏览器 HITL takeover 请求状态)
 * - useBrowserTakeoverActions (POS: takeover 完成/跳过与会话恢复动作)
 * - scheduleMobilePairRefresh (POS: 移动端 pair token 续期调度)
 *
 * [OUTPUT]
 * - MobileTakeoverBoard: 移动端接管落地页（展示上下文并执行 Done/Skip）
 *
 * [POS]
 * - /mobile/takeover/[chatId] 页面主体，承接签名链接参数并触发 takeover resume。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Activity, ArrowLeft, CheckCircle2, ExternalLink, Maximize2, XCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { mobileApiRequest, scheduleMobilePairRefresh } from '@/lib/mobileRemote';
import { useBrowserTakeoverActions } from '@/hooks/useBrowserTakeoverActions';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useChatStore from '@/store/useChatStore';
import { Button } from '@/components/primitives/button';

const TAKEOVER_REASON_MAX_CHARS = 280;
const TAKEOVER_PAGE_URL_MAX_CHARS = 1024;
const TAKEOVER_PREVIEW_POLL_MS = 2500;

interface BrowserTakeoverSnapshotResponse {
  screenshot_base64: string;
  mime_type: string;
  refs: Record<string, unknown>;
  page_url: string;
  page_title: string;
  viewport_width: number;
  viewport_height: number;
}

interface BrowserTakeoverPreview {
  screenshotBase64: string;
  mimeType: string;
  pageUrl: string;
  pageTitle: string;
  updatedAt: number;
}

function clampQueryParam(value: string | null, maxChars: number): string {
  if (!value) {
    return '';
  }
  const trimmed = value.trim();
  return trimmed ? trimmed.slice(0, maxChars) : '';
}

export default function MobileTakeoverBoard({ chatId }: { chatId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useTranslations('billing.vnc');
  const tMobile = useTranslations('agent.mobileCommand');
  const [ready, setReady] = useState(false);
  const [preview, setPreview] = useState<BrowserTakeoverPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(true);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);

  const takeoverMessageId = searchParams.get('mid')?.trim() ?? '';
  const takeoverReason = clampQueryParam(searchParams.get('reason'), TAKEOVER_REASON_MAX_CHARS);
  const takeoverPageUrl = clampQueryParam(searchParams.get('page'), TAKEOVER_PAGE_URL_MAX_CHARS);
  const pairToken = searchParams.get('pair')?.trim() ?? '';

  const pending = useBrowserTakeoverStore((state) => state.pending);
  const reason = useBrowserTakeoverStore((state) => state.reason);
  const pageUrl = useBrowserTakeoverStore((state) => state.url);
  const { handleTakeoverComplete, handleTakeoverSkip } = useBrowserTakeoverActions();

  const refreshPreview = useCallback(async (): Promise<boolean> => {
    const payload = await mobileApiRequest<BrowserTakeoverSnapshotResponse>(
      `/api/v1/remote-access/mobile/takeover/${encodeURIComponent(chatId)}/snapshot`,
    );
    setPreview({
      screenshotBase64: payload.screenshot_base64,
      mimeType: payload.mime_type,
      pageUrl: payload.page_url,
      pageTitle: payload.page_title,
      updatedAt: Date.now(),
    });
    return Boolean(payload.screenshot_base64);
  }, [chatId]);

  useEffect(() => {
    return scheduleMobilePairRefresh();
  }, []);

  useEffect(() => {
    if (!pending || !takeoverMessageId) {
      setPreviewLoading(false);
      return;
    }

    setPreviewLoading(true);
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        await refreshPreview();
      } catch {
        // Keep current preview snapshot if the poll fails transiently.
      } finally {
        if (!cancelled) {
          setPreviewLoading(false);
          timer = setTimeout(() => {
            void poll();
          }, TAKEOVER_PREVIEW_POLL_MS);
        }
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [pending, refreshPreview, takeoverMessageId]);

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

  useEffect(() => {
    if (!lightboxSrc) return;
    document.body.style.overflow = 'hidden';
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setLightboxSrc(null);
      }
    };
    window.addEventListener('keydown', handler);
    return () => {
      document.body.style.overflow = '';
      window.removeEventListener('keydown', handler);
    };
  }, [lightboxSrc]);

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
  const previewAgeSeconds = preview?.updatedAt ? Math.round((Date.now() - preview.updatedAt) / 1000) : null;

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

        <section className="rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm backdrop-blur">
          <div className="mb-3 flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-medium">{tMobile('livePreview')}</h2>
            {previewAgeSeconds !== null ? (
              <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">
                {previewAgeSeconds < 60 ? `${previewAgeSeconds}s` : `${Math.floor(previewAgeSeconds / 60)}m`}
              </span>
            ) : null}
          </div>

          {previewLoading && !preview ? (
            <div className="h-36 animate-pulse rounded-xl bg-muted/30" />
          ) : preview?.screenshotBase64 ? (
            <button
              type="button"
              className="relative w-full overflow-hidden rounded-xl bg-muted/20 group"
              onClick={() => setLightboxSrc(`data:${preview.mimeType};base64,${preview.screenshotBase64}`)}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`data:${preview.mimeType};base64,${preview.screenshotBase64}`}
                alt={tMobile('livePreview')}
                className="max-h-56 w-full object-contain"
                draggable={false}
              />
              <div className="absolute right-2 top-2 rounded-md bg-black/40 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100">
                <Maximize2 className="h-3.5 w-3.5" />
              </div>
            </button>
          ) : (
            <p className="rounded-xl bg-muted/20 px-3 py-4 text-xs text-muted-foreground">{t('takeoverExtensionHint')}</p>
          )}

          {preview?.pageUrl ? (
            <a
              href={preview.pageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex max-w-full items-center gap-1 text-xs text-primary hover:underline"
            >
              <ExternalLink className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{preview.pageTitle || preview.pageUrl}</span>
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

      {lightboxSrc ? (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4"
          onClick={() => setLightboxSrc(null)}
          role="dialog"
          aria-modal="true"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={lightboxSrc}
            alt={tMobile('livePreview')}
            className="max-h-full max-w-full rounded-lg object-contain"
            draggable={false}
            onClick={(event) => event.stopPropagation()}
          />
        </div>
      ) : null}
    </main>
  );
}
