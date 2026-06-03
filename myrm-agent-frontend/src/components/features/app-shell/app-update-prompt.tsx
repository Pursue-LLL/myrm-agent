'use client';

/**
 * [POS] Tauri 桌面端自动更新提示组件
 *
 * 静默下载模式：checking/available/downloading 阶段不可见。
 * 仅在 ready/installing/restarting/error 阶段展示底部右侧浮层。
 * 非 Tauri 环境渲染 null。
 */

import { useCallback, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslations } from 'next-intl';

import { isTauriRuntime } from '@/lib/deploy-mode';
import { useAppUpdate, type AppUpdatePhase } from '@/hooks/useAppUpdate';
import { IconX } from '@/components/features/icons/PremiumIcons';

function shouldShow(phase: AppUpdatePhase): boolean {
  return phase === 'ready' || phase === 'installing' || phase === 'restarting' || phase === 'error';
}

const UpdateIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
    <path d="M10 2a8 8 0 015.292 13.97v1.78a.75.75 0 01-1.5 0v-1.06a.75.75 0 01.22-.53A6.5 6.5 0 1010 16.5a.75.75 0 010 1.5A8 8 0 1110 2z" />
    <path d="M9.25 6.75a.75.75 0 011.5 0v3.69l2.22 2.22a.75.75 0 11-1.06 1.06l-2.44-2.44a.75.75 0 01-.22-.53V6.75z" />
  </svg>
);

export function AppUpdatePrompt() {
  const t = useTranslations('appUpdate');
  const { phase, info, error, install, check, reset } = useAppUpdate();

  const [dismissed, setDismissed] = useState(false);
  const [prevPhase, setPrevPhase] = useState(phase);
  const dismissedErrorRef = useRef<string | null>(null);
  const currentErrorKey = error ?? 'unknown';

  if (phase !== prevPhase) {
    setPrevPhase(phase);
    if (shouldShow(phase) && !shouldShow(prevPhase)) {
      setDismissed(phase === 'error' && dismissedErrorRef.current === currentErrorKey);
    }
  }

  const handleInstall = useCallback(() => {
    void install();
  }, [install]);

  const handleLater = useCallback(() => {
    setDismissed(true);
  }, []);

  const handleRetry = useCallback(() => {
    dismissedErrorRef.current = null;
    setDismissed(false);
    reset();
    void check();
  }, [reset, check]);

  const handleDismissError = useCallback(() => {
    dismissedErrorRef.current = currentErrorKey;
    reset();
    setDismissed(true);
  }, [currentErrorKey, reset]);

  if (!isTauriRuntime() || !shouldShow(phase) || dismissed) return null;
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 left-4 right-4 z-[9998] sm:left-auto sm:right-4 sm:w-[340px] animate-in slide-in-from-bottom-4 fade-in duration-300"
      data-testid="app-update-prompt"
    >
      <div className="bg-background border border-border rounded-2xl shadow-lg overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-3 pb-1">
          <div className="flex items-center gap-2">
            <UpdateIcon className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium text-foreground">
              {phase === 'ready' && t('readyTitle')}
              {phase === 'installing' && t('installingTitle')}
              {phase === 'restarting' && t('restartingTitle')}
              {phase === 'error' && t('errorTitle')}
            </span>
          </div>
          {(phase === 'ready' || phase === 'error') && (
            <button
              onClick={phase === 'error' ? handleDismissError : handleLater}
              className="p-1 text-muted-foreground hover:text-foreground transition-colors"
              aria-label={t('dismiss')}
            >
              <IconX className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-4 pt-1 pb-3">
          {phase === 'ready' && (
            <>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {info?.version ? t('readyDescription', { version: info.version }) : t('readyDescriptionGeneric')}
                {info?.currentVersion && (
                  <span className="text-muted-foreground/60">
                    {' '}
                    {t('currentVersion', { version: info.currentVersion })}
                  </span>
                )}
              </p>
              {info?.body && <ReleaseNotes body={info.body} />}
              <p className="mt-2 text-[11px] text-muted-foreground/60 leading-relaxed">{t('restartHint')}</p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={handleInstall}
                  className="flex-1 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium transition-colors"
                >
                  {t('restartNow')}
                </button>
                <button
                  onClick={handleLater}
                  className="px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:bg-muted text-xs transition-colors"
                >
                  {t('later')}
                </button>
              </div>
            </>
          )}

          {(phase === 'installing' || phase === 'restarting') && (
            <>
              <ProgressBar indeterminate />
              <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>{phase === 'installing' ? t('installingProgress') : t('restartingProgress')}</span>
                {info?.version && <span className="text-muted-foreground/60">v{info.version}</span>}
              </div>
            </>
          )}

          {phase === 'error' && (
            <>
              <p className="text-xs text-destructive leading-relaxed">{error ?? t('errorGeneric')}</p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={handleRetry}
                  className="flex-1 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium transition-colors"
                >
                  {t('retry')}
                </button>
                <button
                  onClick={handleDismissError}
                  className="px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:bg-muted text-xs transition-colors"
                >
                  {t('dismiss')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

function ProgressBar({ indeterminate, percent }: { indeterminate?: boolean; percent?: number | null }) {
  const isIndet = indeterminate || percent == null;
  return (
    <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
      <div
        className={`h-full rounded-full bg-primary transition-all duration-500 ${isIndet ? 'animate-pulse' : ''}`}
        style={{ width: isIndet ? '100%' : `${percent ?? 0}%` }}
      />
    </div>
  );
}

function ReleaseNotes({ body }: { body: string }) {
  const t = useTranslations('appUpdate');
  const [expanded, setExpanded] = useState(false);
  const trimmed = body.trim();
  if (!trimmed) return null;
  const isLong = trimmed.length > 160;
  const display = expanded || !isLong ? trimmed : `${trimmed.slice(0, 160).trimEnd()}…`;
  return (
    <div className="mt-2 rounded-lg bg-muted/60 border border-border/40 px-3 py-2">
      <p className="text-[11px] text-muted-foreground whitespace-pre-line break-words">{display}</p>
      {isLong && (
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className="mt-1 text-[11px] text-primary hover:text-primary/80 transition-colors"
        >
          {expanded ? t('showLess') : t('showMore')}
        </button>
      )}
    </div>
  );
}
