'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import type { WeChatOfficialCredentials } from '@/services/channels';
import {
  getWeChatOfficialCredentials,
  getWeChatOfficialEgressIp,
  saveWeChatOfficialCredentials,
  testWeChatOfficialConnection,
} from '@/services/channels';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { toast } from 'sonner';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: WeChatOfficialCredentials = {
  appId: '',
  appSecret: '',
  token: '',
  encodingAesKey: '',
};

export function WeChatOfficialConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);
  const [egressIp, setEgressIp] = useState<string | null>(null);
  const [egressLoading, setEgressLoading] = useState(true);
  const [egressError, setEgressError] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<WeChatOfficialCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['appId', 'appSecret'],
      getCreds: getWeChatOfficialCredentials,
      saveCreds: saveWeChatOfficialCredentials,
      testConnection: (c) => testWeChatOfficialConnection(c.appId, c.appSecret),
      i18nPrefix: 'wechatOfficial',
    });

  const loadEgressIp = useCallback(async () => {
    setEgressLoading(true);
    setEgressError(false);
    try {
      const result = await getWeChatOfficialEgressIp();
      setEgressIp(result.egressIp);
    } catch {
      setEgressIp(null);
      setEgressError(true);
    } finally {
      setEgressLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadEgressIp();
  }, [loadEgressIp]);

  const handleCopyEgressIp = useCallback(async () => {
    if (!egressIp) {
      return;
    }
    const copied = await writeToClipboard(egressIp);
    if (copied) {
      toast.success(t('wechatOfficialEgressCopied'));
    } else {
      toast.error(t('wechatOfficialEgressCopyFailed'));
    }
  }, [egressIp, t]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <IconLoader className="h-4 w-4 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="wechat-official-config-card">
      <p className="text-xs text-muted-foreground">{t('wechatOfficialDesc')}</p>
      <div
        className="rounded-lg border border-border/60 bg-muted/20 p-3 space-y-2"
        data-testid="wechat-official-egress-ip-panel"
      >
        <p className="text-xs text-muted-foreground leading-relaxed">{t('wechatOfficialIpWhitelistHint')}</p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1">
            <Label className="text-xs text-muted-foreground">{t('wechatOfficialEgressLabel')}</Label>
            {egressLoading ? (
              <p className="mt-1 text-sm text-muted-foreground">{t('wechatOfficialEgressLoading')}</p>
            ) : egressError || !egressIp ? (
              <p className="mt-1 text-sm text-destructive">{t('wechatOfficialEgressUnavailable')}</p>
            ) : (
              <p className="mt-1 font-mono text-sm text-foreground" data-testid="wechat-official-egress-ip">
                {egressIp}
              </p>
            )}
          </div>
          <div className="flex shrink-0 gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={egressLoading || !egressIp}
              onClick={() => void handleCopyEgressIp()}
            >
              {t('wechatOfficialEgressCopy')}
            </Button>
            <Button type="button" variant="ghost" size="sm" disabled={egressLoading} onClick={() => void loadEgressIp()}>
              {t('wechatOfficialEgressRefresh')}
            </Button>
          </div>
        </div>
      </div>
      <ConnectionBadge status={connStatus} label={statusLabel} />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="wechat-official-app-id">{t('wechatOfficialAppId')}</Label>
          <Input
            id="wechat-official-app-id"
            placeholder="wx..."
            value={creds.appId}
            onChange={(e) => handleChange('appId', e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="wechat-official-app-secret">{t('wechatOfficialAppSecret')}</Label>
          <div className="relative">
            <Input
              id="wechat-official-app-secret"
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
          <Label htmlFor="wechat-official-token">{t('wechatOfficialToken')}</Label>
          <Input
            id="wechat-official-token"
            placeholder={t('wechatOfficialTokenHint')}
            value={creds.token}
            onChange={(e) => handleChange('token', e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="wechat-official-aes-key">{t('wechatOfficialEncodingAesKey')}</Label>
          <Input
            id="wechat-official-aes-key"
            placeholder={t('wechatOfficialEncodingAesKeyHint')}
            value={creds.encodingAesKey}
            onChange={(e) => handleChange('encodingAesKey', e.target.value)}
          />
        </div>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('wechatOfficialSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.appId || !creds.appSecret}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('wechatOfficialTestConnection')}
        </Button>
      </div>
    </div>
  );
}
