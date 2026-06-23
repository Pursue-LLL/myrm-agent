'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { useChannelLogin } from './useChannelLogin';
import type { ChannelLoginPhase } from './useChannelLogin';

interface ChannelLoginDialogProps {
  channelId: string;
  channelLabel: string;
  loginMethod?: string;
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

/**
 * Generic QR code login dialog for IM channels (WeChat, WhatsApp, etc.).
 *
 * Consumes the existing AsyncLoginProtocol backend via SSE streaming.
 * Features: real-time status, auto QR refresh (backend-driven), cancel, cleanup.
 */
export function ChannelLoginDialog({
  channelId,
  channelLabel,
  loginMethod = 'qr_code',
  open,
  onClose,
  onSuccess,
}: ChannelLoginDialogProps) {
  const t = useTranslations('channels');
  const dialogRef = useRef<HTMLDialogElement>(null);

  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;

  const handleSuccess = useCallback(() => {
    onSuccessRef.current?.();
    setTimeout(() => onCloseRef.current(), 1500);
  }, []);

  const { phase, qrCodeBase64, errorMessage, start, cancel, reset } = useChannelLogin(
    channelId,
    loginMethod,
    handleSuccess,
  );

  const startRef = useRef(start);
  startRef.current = start;
  const resetRef = useRef(reset);
  resetRef.current = reset;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      if (!dialog.open) dialog.showModal();
      startRef.current();
    } else {
      if (dialog.open) dialog.close();
      resetRef.current();
    }
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleClose = () => {
      if (phase !== 'success') cancel();
      onClose();
    };
    dialog.addEventListener('close', handleClose);
    return () => dialog.removeEventListener('close', handleClose);
  }, [phase, cancel, onClose]);

  return (
    <dialog
      ref={dialogRef}
      className="fixed inset-0 z-50 m-auto w-full max-w-sm rounded-xl border border-border bg-background p-0 shadow-2xl backdrop:bg-black/40"
    >
      <div className="flex flex-col items-center gap-4 p-6">
        <h3 className="text-lg font-semibold">
          {t('qrLoginTitle', { channel: channelLabel })}
        </h3>

        <QrContent
          phase={phase}
          qrCodeBase64={qrCodeBase64}
          errorMessage={errorMessage}
          channelLabel={channelLabel}
          t={t}
        />

        <PhaseHint phase={phase} t={t} />

        <div className="flex w-full gap-3">
          {(phase === 'failed' || phase === 'cancelled') && (
            <button
              type="button"
              onClick={start}
              className="flex-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              {t('qrLoginRetry')}
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              if (phase !== 'success') cancel();
              onClose();
            }}
            className="flex-1 rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
          >
            {phase === 'success' ? t('qrLoginDone') : t('qrLoginCancel')}
          </button>
        </div>
      </div>
    </dialog>
  );
}

function QrContent({
  phase,
  qrCodeBase64,
  errorMessage,
  channelLabel,
  t,
}: {
  phase: ChannelLoginPhase;
  qrCodeBase64: string | null;
  errorMessage: string | null;
  channelLabel: string;
  t: ReturnType<typeof useTranslations<'channels'>>;
}) {
  if (phase === 'starting') {
    return (
      <div className="flex h-52 w-52 items-center justify-center rounded-lg bg-muted">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (phase === 'waiting_qr' && qrCodeBase64) {
    const src = qrCodeBase64.startsWith('data:')
      ? qrCodeBase64
      : `data:image/png;base64,${qrCodeBase64}`;
    return (
      <div className="flex flex-col items-center gap-2">
        <img src={src} alt="QR Code" className="h-52 w-52 rounded-lg" />
        <p className="text-center text-xs text-muted-foreground">
          {t('qrLoginScanHint', { channel: channelLabel })}
        </p>
      </div>
    );
  }

  if (phase === 'scanned') {
    return (
      <div className="flex h-52 w-52 flex-col items-center justify-center gap-2 rounded-lg bg-muted">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">{t('qrLoginValidating')}</p>
      </div>
    );
  }

  if (phase === 'success') {
    return (
      <div className="flex h-52 w-52 flex-col items-center justify-center gap-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/20">
        <svg className="h-12 w-12 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
        <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
          {t('qrLoginSuccess')}
        </p>
      </div>
    );
  }

  if (phase === 'failed') {
    return (
      <div className="flex h-52 w-52 flex-col items-center justify-center gap-2 rounded-lg bg-red-50 dark:bg-red-950/20">
        <svg className="h-12 w-12 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
        <p className="text-sm text-red-600 dark:text-red-400">
          {errorMessage ?? t('qrLoginFailed')}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-52 w-52 items-center justify-center rounded-lg bg-muted">
      <p className="text-sm text-muted-foreground">{t('qrLoginIdle')}</p>
    </div>
  );
}

function PhaseHint({
  phase,
  t,
}: {
  phase: ChannelLoginPhase;
  t: ReturnType<typeof useTranslations<'channels'>>;
}) {
  const hints: Partial<Record<ChannelLoginPhase, string>> = {
    starting: t('qrLoginGenerating'),
    waiting_qr: t('qrLoginWaiting'),
    scanned: t('qrLoginValidating'),
    success: t('qrLoginConnected'),
  };
  const hint = hints[phase];
  if (!hint) return null;
  return <p className="text-center text-sm text-muted-foreground">{hint}</p>;
}
