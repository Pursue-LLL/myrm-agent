'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { QRCodeSVG } from 'qrcode.react';
import { Button } from '@/components/primitives/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { ApiError, apiRequest } from '@/lib/api';

interface QRRegisterResponse {
  session_id: string;
  qr_url: string;
  expire_in: number;
  interval: number;
}

interface QRPollResponse {
  status: 'pending' | 'success' | 'denied' | 'expired';
  credentials?: {
    appId: string;
    appSecret: string;
    useLark: string;
  };
  instance_id?: string | null;
  channel_name?: string | null;
}

type QrStatus = 'idle' | 'loading' | 'scanning' | 'success' | 'failed' | 'unsupported';

interface FeishuQrRegisterDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When set, the registered bot is provisioned as a new multi-app instance. */
  displayName?: string;
  /** Show the app label input (multi-app flow). Hidden for default-instance refresh. */
  allowLabel?: boolean;
  onSuccess?: (result?: { instanceId?: string | null; channelName?: string | null }) => void;
}

export function FeishuQrRegisterDialog({
  open,
  onOpenChange,
  displayName,
  allowLabel = false,
  onSuccess,
}: FeishuQrRegisterDialogProps) {
  const t = useTranslations('channels');
  const [qrStatus, setQrStatus] = useState<QrStatus>('idle');
  const [qrUrl, setQrUrl] = useState('');
  const [qrCountdown, setQrCountdown] = useState(0);
  const [appLabel, setAppLabel] = useState(displayName ?? '');
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const resolvedRef = useRef(false);

  const cleanupTimers = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    if (countdownTimerRef.current) {
      clearInterval(countdownTimerRef.current);
      countdownTimerRef.current = null;
    }
  }, []);

  useEffect(() => cleanupTimers, [cleanupTimers]);

  useEffect(() => {
    if (open) {
      setAppLabel(displayName ?? '');
      setQrStatus('idle');
      setQrUrl('');
      setQrCountdown(0);
      resolvedRef.current = false;
    } else {
      cleanupTimers();
      setQrStatus('idle');
      setQrUrl('');
      resolvedRef.current = false;
    }
  }, [open, displayName, cleanupTimers]);

  const handleStartQRRegister = useCallback(async () => {
    resolvedRef.current = false;
    setQrStatus('loading');
    try {
      const body: Record<string, string> = {};
      if (appLabel.trim()) {
        body.display_name = appLabel.trim();
      }
      const res = await apiRequest<QRRegisterResponse>('/channels/manage/feishu/qr-register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setQrUrl(res.qr_url);
      setQrStatus('scanning');
      setQrCountdown(res.expire_in);

      countdownTimerRef.current = setInterval(() => {
        setQrCountdown((prev) => {
          if (prev <= 1) {
            cleanupTimers();
            setQrStatus('failed');
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      pollTimerRef.current = setInterval(
        async () => {
          try {
            const poll = await apiRequest<QRPollResponse>('/channels/manage/feishu/qr-register/poll', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ session_id: res.session_id }),
            });

            if (poll.status === 'success') {
              resolvedRef.current = true;
              cleanupTimers();
              setQrStatus('success');
              onSuccess?.({ instanceId: poll.instance_id ?? null, channelName: poll.channel_name ?? null });
              setTimeout(() => onOpenChange(false), 1500);
            } else if (poll.status === 'denied' || poll.status === 'expired') {
              resolvedRef.current = true;
              cleanupTimers();
              setQrStatus('failed');
            }
          } catch (err) {
            // Ignore failures after a terminal status was already reached:
            // an in-flight poll may 404 because the winning poll consumed the
            // session, and must not overwrite `success` with `failed`.
            if (!resolvedRef.current && err instanceof ApiError) {
              resolvedRef.current = true;
              cleanupTimers();
              // HTTP error means the session was dropped server-side (404),
              // provisioning failed (500), or the service is unavailable (503).
              // Fail fast instead of scanning until expiry.
              setQrStatus('failed');
            }
            /* network hiccup, keep polling */
          }
        },
        (res.interval || 5) * 1000,
      );
    } catch (err) {
      setQrStatus(err instanceof ApiError && err.code === 503 ? 'unsupported' : 'failed');
    }
  }, [appLabel, cleanupTimers, onOpenChange, onSuccess]);

  const handleClose = useCallback(() => {
    cleanupTimers();
    onOpenChange(false);
  }, [cleanupTimers, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('feishuQrDialogTitle')}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col items-center gap-4 py-4">
          {qrStatus === 'idle' && (
            <div className="w-full space-y-3">
              {allowLabel && (
                <div className="space-y-2">
                  <Label htmlFor="feishu-new-app-label">{t('feishuAppLabelPlaceholder')}</Label>
                  <Input
                    id="feishu-new-app-label"
                    placeholder={t('feishuAppLabelPlaceholder')}
                    value={appLabel}
                    onChange={(e) => setAppLabel(e.target.value)}
                    maxLength={50}
                  />
                  {!appLabel.trim() && <p className="text-xs text-destructive">{t('feishuAppLabelRequired')}</p>}
                </div>
              )}
              <Button
                className="w-full"
                onClick={() => void handleStartQRRegister()}
                disabled={allowLabel && !appLabel.trim()}
                title={allowLabel && !appLabel.trim() ? t('feishuAppLabelRequired') : undefined}
              >
                <span>{allowLabel ? t('feishuScanToAdd') : t('feishuQrButton')}</span>
              </Button>
            </div>
          )}
          {qrStatus === 'loading' && (
            <div className="flex h-48 w-48 items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-3 border-primary border-t-transparent" />
            </div>
          )}
          {qrStatus === 'scanning' && qrUrl && (
            <>
              <div className="rounded-xl bg-white p-4">
                <QRCodeSVG value={qrUrl} size={192} level="M" />
              </div>
              <p className="text-sm text-muted-foreground">{t('feishuQrScanHint')}</p>
              <p className="text-xs text-muted-foreground/70">{t('feishuQrExpireIn', { seconds: qrCountdown })}</p>
            </>
          )}
          {qrStatus === 'success' && (
            <div className="flex flex-col items-center gap-2 py-8">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 15 15"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                  className="text-green-600 dark:text-green-400"
                >
                  <path
                    d="M11.4669 3.72684C11.7558 3.91574 11.8369 4.30308 11.648 4.59198L7.39799 11.092C7.29783 11.2452 7.13556 11.3467 6.95402 11.3699C6.77247 11.3931 6.58989 11.3355 6.45446 11.2124L3.70446 8.71241C3.44905 8.48022 3.43023 8.08494 3.66242 7.82953C3.89461 7.57412 4.28989 7.5553 4.5453 7.78749L6.75292 9.79441L10.6018 3.90792C10.7907 3.61902 11.178 3.53795 11.4669 3.72684Z"
                    fill="currentColor"
                    fillRule="evenodd"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <p className="text-sm font-medium">{t('feishuQrSuccess')}</p>
            </div>
          )}
          {qrStatus === 'unsupported' && (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <p className="text-sm text-muted-foreground">{t('feishuQrUnsupported')}</p>
              <Button size="sm" variant="outline" onClick={handleClose}>
                {t('feishuQrManualFallback')}
              </Button>
            </div>
          )}
          {qrStatus === 'failed' && (
            <div className="flex flex-col items-center gap-3 py-8">
              <p className="text-sm text-muted-foreground">{t('feishuQrFailed')}</p>
              <Button size="sm" variant="outline" onClick={() => void handleStartQRRegister()}>
                {t('feishuQrRetry')}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
