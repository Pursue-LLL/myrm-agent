'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { QRCodeSVG } from 'qrcode.react';
import { Button } from '@/components/primitives/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { IconEye, IconEyeOff, IconQrCode } from '@/components/features/icons/PremiumIcons';
import type { FeishuCredentials } from '@/services/channels';
import { getFeishuCredentials, saveFeishuCredentials, testFeishuConnection } from '@/services/channels';
import { ApiError, apiRequest } from '@/lib/api';
import { isLocalMode } from '@/lib/deploy-mode';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

type RenderMode = FeishuCredentials['renderMode'];

const EMPTY_CREDS: FeishuCredentials = {
  appId: '',
  appSecret: '',
  botOpenId: '',
  verificationToken: '',
  encryptKey: '',
  useLark: false,
  renderMode: 'auto',
  transport: 'websocket',
  botPolicy: 'deny',
};

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
    botOpenId: string;
  };
}

export function FeishuConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);
  const [qrDialogOpen, setQrDialogOpen] = useState(false);
  const [qrUrl, setQrUrl] = useState('');
  const [qrStatus, setQrStatus] = useState<'idle' | 'loading' | 'scanning' | 'success' | 'failed' | 'unsupported'>(
    'idle',
  );
  const [qrCountdown, setQrCountdown] = useState(0);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const {
    creds,
    dirty,
    loading,
    saving,
    testing,
    connStatus,
    statusLabel,
    handleChange,
    handleSave,
    handleTest,
    refreshCreds,
  } = useChannelConfig<FeishuCredentials>({
    emptyCreds: EMPTY_CREDS,
    requiredFields: ['appId', 'appSecret'],
    getCreds: getFeishuCredentials,
    saveCreds: saveFeishuCredentials,
    testConnection: (c) => testFeishuConnection(c.appId, c.appSecret, c.useLark),
    i18nPrefix: 'feishu',
  });

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

  const handleStartQRRegister = useCallback(async () => {
    setQrStatus('loading');
    setQrDialogOpen(true);
    try {
      const res = await apiRequest<QRRegisterResponse>('/channels/manage/feishu/qr-register', {
        method: 'POST',
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
              cleanupTimers();
              setQrStatus('success');
              refreshCreds?.();
              setTimeout(() => setQrDialogOpen(false), 1500);
            } else if (poll.status === 'denied' || poll.status === 'expired') {
              cleanupTimers();
              setQrStatus('failed');
            }
          } catch {
            /* network hiccup, keep polling */
          }
        },
        (res.interval || 5) * 1000,
      );
    } catch (err) {
      setQrStatus(err instanceof ApiError && err.code === 503 ? 'unsupported' : 'failed');
    }
  }, [cleanupTimers, refreshCreds]);

  const handleCloseQRDialog = useCallback(() => {
    cleanupTimers();
    setQrDialogOpen(false);
    setQrStatus('idle');
    setQrUrl('');
  }, [cleanupTimers]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ConnectionBadge status={connStatus} label={statusLabel} />

      {!creds.appId && (
        <div className="rounded-lg border border-dashed border-primary/30 bg-primary/5 p-4">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2">
              <IconQrCode className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 space-y-2">
              <p className="text-sm font-medium">{t('feishuQrTitle')}</p>
              <p className="text-xs text-muted-foreground">{t('feishuQrDescription')}</p>
              <Button size="sm" onClick={handleStartQRRegister} disabled={qrStatus === 'loading'}>
                {qrStatus === 'loading' && (
                  <div className="mr-2 h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                )}
                <IconQrCode className="mr-2 h-3.5 w-3.5" />
                {t('feishuQrButton')}
              </Button>
            </div>
          </div>
        </div>
      )}

      <Dialog open={qrDialogOpen} onOpenChange={(open) => !open && handleCloseQRDialog()}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('feishuQrDialogTitle')}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col items-center gap-4 py-4">
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
                <Button size="sm" variant="outline" onClick={handleCloseQRDialog}>
                  {t('feishuQrManualFallback')}
                </Button>
              </div>
            )}
            {qrStatus === 'failed' && (
              <div className="flex flex-col items-center gap-3 py-8">
                <p className="text-sm text-muted-foreground">{t('feishuQrFailed')}</p>
                <Button size="sm" variant="outline" onClick={handleStartQRRegister}>
                  {t('feishuQrRetry')}
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="feishu-app-id">{t('feishuAppId')}</Label>
          <Input
            id="feishu-app-id"
            placeholder="cli_xxxxx"
            value={creds.appId}
            onChange={(e) => handleChange('appId', e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="feishu-app-secret">{t('feishuAppSecret')}</Label>
          <div className="relative">
            <Input
              id="feishu-app-secret"
              type={showSecret ? 'text' : 'password'}
              placeholder="••••••••"
              value={creds.appSecret}
              onChange={(e) => handleChange('appSecret', e.target.value)}
              className="pr-10"
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
              onClick={() => setShowSecret(!showSecret)}
            >
              {showSecret ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="feishu-bot-id">{t('feishuBotOpenId')}</Label>
          <Input
            id="feishu-bot-id"
            placeholder="ou_xxxxx"
            value={creds.botOpenId}
            onChange={(e) => handleChange('botOpenId', e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('feishuBotOpenIdHint')}</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="feishu-token">{t('feishuVerificationToken')}</Label>
          <Input
            id="feishu-token"
            placeholder={t('feishuOptional')}
            value={creds.verificationToken}
            onChange={(e) => handleChange('verificationToken', e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('feishuVerificationTokenHint')}</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="feishu-encrypt-key">{t('feishuEncryptKey')}</Label>
          <Input
            id="feishu-encrypt-key"
            placeholder={t('feishuOptional')}
            value={creds.encryptKey}
            onChange={(e) => handleChange('encryptKey', e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('feishuEncryptKeyHint')}</p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label>{t('feishuTransport')}</Label>
          <Select value={creds.transport} onValueChange={(v: 'webhook' | 'websocket') => handleChange('transport', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="webhook">{t('feishuTransportWebhook')}</SelectItem>
              <SelectItem value="websocket">
                <div className="flex items-center gap-2">
                  {t('feishuTransportWebsocket')}
                  {isLocalMode() && (
                    <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-500">
                      {t('feishuTransportLocalRecommended')}
                    </span>
                  )}
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{t('feishuTransportHint')}</p>
          {isLocalMode() && creds.transport === 'webhook' && (
            <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3">
              <p className="text-xs leading-relaxed text-amber-600 dark:text-amber-400/90">
                {t('feishuWebhookLocalWarning')}{' '}
                <Link
                  href="/settings/system#public-access"
                  className="font-medium underline underline-offset-2 hover:text-amber-500"
                >
                  {t('feishuWebhookLocalWarningLink')}
                </Link>
              </p>
            </div>
          )}
        </div>

        <div className="space-y-2">
          <Label>{t('feishuRenderMode')}</Label>
          <Select value={creds.renderMode} onValueChange={(v: RenderMode) => handleChange('renderMode', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">{t('feishuRenderAuto')}</SelectItem>
              <SelectItem value="raw">{t('feishuRenderRaw')}</SelectItem>
              <SelectItem value="card">{t('feishuRenderCard')}</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{t('feishuRenderModeHint')}</p>
        </div>

        <div className="space-y-2">
          <Label>{t('feishuUseLark')}</Label>
          <div className="flex items-center gap-2 pt-1.5">
            <Switch checked={creds.useLark} onCheckedChange={(v) => handleChange('useLark', v)} />
            <span className="text-xs text-muted-foreground">{t('feishuUseLarkHint')}</span>
          </div>
        </div>

        <div className="space-y-2">
          <Label>{t('feishuBotPolicy')}</Label>
          <Select
            value={creds.botPolicy}
            onValueChange={(v: 'deny' | 'mention_only' | 'allow') => handleChange('botPolicy', v)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="deny">{t('feishuBotPolicyDeny')}</SelectItem>
              <SelectItem value="mention_only">{t('feishuBotPolicyMentionOnly')}</SelectItem>
              <SelectItem value="allow">{t('feishuBotPolicyAllow')}</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{t('feishuBotPolicyHint')}</p>
        </div>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && (
            <div className="mr-2 h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
          )}
          {t('feishuSave')}
        </Button>

        <Button variant="outline" onClick={handleTest} disabled={testing || !creds.appId || !creds.appSecret} size="sm">
          {testing && (
            <div className="mr-2 h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
          )}
          {t('feishuTestConnection')}
        </Button>

        {creds.appId && (
          <Button variant="ghost" onClick={handleStartQRRegister} size="sm" className="ml-auto">
            <IconQrCode className="mr-2 h-3.5 w-3.5" />
            {t('feishuQrRecreate')}
          </Button>
        )}
      </div>
    </div>
  );
}
