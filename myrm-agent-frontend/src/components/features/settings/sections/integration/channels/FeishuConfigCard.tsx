'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { IconEye, IconEyeOff, IconQrCode } from '@/components/features/icons/PremiumIcons';
import type { FeishuCredentials } from '@/services/channels';
import { getFeishuCredentials, saveFeishuCredentials, testFeishuConnection } from '@/services/channels';
import { isLocalMode } from '@/lib/deploy-mode';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';
import { FeishuMultiAppSection } from './FeishuMultiAppSection';
import { FeishuQrRegisterDialog } from './FeishuQrRegisterDialog';

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

export function FeishuConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);
  const [qrDialogOpen, setQrDialogOpen] = useState(false);

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

  const handleQrSuccess = useCallback(() => {
    refreshCreds?.();
  }, [refreshCreds]);

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
              <Button size="sm" onClick={() => setQrDialogOpen(true)}>
                <IconQrCode className="mr-2 h-3.5 w-3.5" />
                {t('feishuQrButton')}
              </Button>
            </div>
          </div>
        </div>
      )}

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
                  href="/settings/system#public-ingress"
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
          <Button variant="ghost" onClick={() => setQrDialogOpen(true)} size="sm" className="ml-auto">
            <IconQrCode className="mr-2 h-3.5 w-3.5" />
            {t('feishuQrRecreate')}
          </Button>
        )}
      </div>

      <div className="border-t pt-4">
        <FeishuMultiAppSection />
      </div>

      <FeishuQrRegisterDialog open={qrDialogOpen} onOpenChange={setQrDialogOpen} onSuccess={handleQrSuccess} />
    </div>
  );
}
