/**
 * [INPUT]
 * - useBrowserTakeoverStore (POS: 浏览器 HITL takeover 请求状态)
 * - useBrowserTakeoverActions (POS: Complete/Skip 与 VNC resume 同步)
 *
 * [OUTPUT]
 * ExtensionTakeoverBanner: 外部浏览器（CDP/auto/extension）in-chat takeover 横幅
 *
 * [POS]
 * uiMode=extension（harness SSE is_managed=false）时，引导用户在本地 Chrome 完成 HITL 并提供 Done/Skip；managed 由 VisualDesktopToggle 处理。
 * managed 模式由 VisualDesktopToggle 处理，本组件不渲染。
 */

'use client';

import { CheckCircle2, Globe, XCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { useBrowserTakeoverActions } from '@/hooks/useBrowserTakeoverActions';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';

export default function ExtensionTakeoverBanner() {
  const t = useTranslations('billing.vnc');
  const pending = useBrowserTakeoverStore((s) => s.pending);
  const uiMode = useBrowserTakeoverStore((s) => s.uiMode);
  const autoDetectCompletion = useBrowserTakeoverStore((s) => s.autoDetectCompletion);
  const reason = useBrowserTakeoverStore((s) => s.reason);
  const screenshotBase64 = useBrowserTakeoverStore((s) => s.screenshotBase64);
  const url = useBrowserTakeoverStore((s) => s.url);
  const { handleTakeoverComplete, handleTakeoverSkip } = useBrowserTakeoverActions();

  if (!pending || uiMode !== 'extension') {
    return null;
  }

  const awaitingUser = !autoDetectCompletion;

  return (
    <div
      role="alert"
      aria-live="polite"
      className={cn(
        'relative overflow-hidden border-b border-amber-500/20',
        'bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-transparent',
        'backdrop-blur-md supports-[backdrop-filter]:bg-amber-500/5',
      )}
    >
      <div className="absolute inset-y-0 left-0 w-[3px] bg-gradient-to-b from-amber-500/80 via-amber-500 to-amber-500/40" />
      <div className="flex flex-col gap-3 px-3 py-3 pl-4 sm:flex-row sm:items-start sm:justify-between sm:px-4 sm:pl-5">
        <div className="flex min-w-0 flex-1 gap-3">
          {screenshotBase64 ? (
            <img
              src={`data:image/jpeg;base64,${screenshotBase64}`}
              alt=""
              className="h-14 w-20 shrink-0 rounded-md border border-border object-cover sm:h-16 sm:w-24"
            />
          ) : (
            <span
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-full sm:h-9 sm:w-9',
                'bg-amber-500/15 text-amber-600 ring-1 ring-amber-500/25',
                'dark:bg-amber-500/20 dark:text-amber-400 dark:ring-amber-500/30',
              )}
            >
              <Globe className="h-4 w-4" aria-hidden />
            </span>
          )}
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
              {awaitingUser ? t('takeoverExtensionTitle') : t('takeoverCaptchaAuto')}
            </p>
            <p className="text-xs leading-relaxed text-amber-700 dark:text-amber-300">
              {awaitingUser ? t('takeoverExtensionHint') : t('takeoverCaptchaAutoHint')}
            </p>
            {reason ? (
              <p className="text-xs leading-relaxed text-foreground/80 line-clamp-3">{reason}</p>
            ) : null}
            {url ? (
              <p className="truncate text-[11px] text-muted-foreground" title={url}>
                {url}
              </p>
            ) : null}
          </div>
        </div>
        {awaitingUser ? (
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 self-end sm:self-start">
            <button
              type="button"
              onClick={() => void handleTakeoverSkip()}
              className="inline-flex items-center gap-1.5 rounded-md bg-muted px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/80"
            >
              <XCircle size={14} aria-hidden />
              {t('takeoverSkip')}
            </button>
            <button
              type="button"
              onClick={() => void handleTakeoverComplete()}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              <CheckCircle2 size={14} aria-hidden />
              {t('takeoverDone')}
            </button>
          </div>
        ) : (
          <div className="flex shrink-0 items-center gap-2 self-end sm:self-center">
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500 motion-reduce:animate-none" aria-hidden />
            <span className="text-xs text-amber-700 dark:text-amber-300">{t('takeoverCaptchaAuto')}</span>
          </div>
        )}
      </div>
    </div>
  );
}
