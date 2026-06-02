'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { IconCopy, IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { SMSCredentials } from '@/services/channels';
import { getSMSCredentials, saveSMSCredentials, testSMSConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';
import { useIngressUrl } from '@/hooks/useIngressUrl';

const EMPTY_CREDS: SMSCredentials = { accountSid: '', authToken: '', phoneNumber: '' };

export function SMSConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);
  const [copied, setCopied] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<SMSCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['accountSid', 'authToken', 'phoneNumber'],
      getCreds: getSMSCredentials,
      saveCreds: saveSMSCredentials,
      testConnection: (c) => testSMSConnection(c.accountSid, c.authToken, c.phoneNumber),
      i18nPrefix: 'sms',
    });

  const { url: webhookUrl, loading: webhookLoading } = useIngressUrl('/api/v1/channels/sms/webhook');
  const isLocalhost = webhookUrl.includes('localhost') || webhookUrl.includes('127.0.0.1');

  const handleCopyWebhook = async () => {
    await navigator.clipboard.writeText(webhookUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <IconLoader className="h-4 w-4 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ConnectionBadge status={connStatus} label={statusLabel} />

      <div className="space-y-2 max-w-md">
        <Label htmlFor="sms-account-sid">{t('smsAccountSid')}</Label>
        <Input
          id="sms-account-sid"
          placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
          value={creds.accountSid}
          onChange={(e) => handleChange('accountSid', e.target.value)}
        />
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="sms-auth-token">{t('smsAuthToken')}</Label>
        <div className="relative">
          <Input
            id="sms-auth-token"
            type={showSecret ? 'text' : 'password'}
            placeholder="••••••••"
            value={creds.authToken}
            onChange={(e) => handleChange('authToken', e.target.value)}
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

      <div className="space-y-2 max-w-md">
        <Label htmlFor="sms-phone-number">{t('smsPhoneNumber')}</Label>
        <Input
          id="sms-phone-number"
          placeholder="+15551234567"
          value={creds.phoneNumber}
          onChange={(e) => handleChange('phoneNumber', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('smsPhoneNumberHint')}</p>
      </div>

      <div className="space-y-2 max-w-md">
        <Label>{t('smsWebhookUrl')}</Label>
        <div className="flex items-center gap-2">
          {webhookLoading ? (
            <div className="h-9 flex-1 bg-muted rounded-full animate-pulse" />
          ) : (
            <Input readOnly value={webhookUrl} className="font-mono text-xs bg-muted" />
          )}
          <Button
            variant="outline"
            size="icon"
            onClick={handleCopyWebhook}
            className="shrink-0"
            disabled={webhookLoading}
          >
            <IconCopy className="h-3.5 w-3.5" />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{copied ? t('smsCopied') : t('smsWebhookUrlHint')}</p>
        {!webhookLoading && isLocalhost && (
          <p className="text-xs text-amber-500 mt-1 leading-relaxed">
            {t('smsLocalhostWarning')}{' '}
            <Link href="/settings/system#public-access" className="underline font-medium hover:text-amber-400">
              {t('smsOpenSystemSettings')}
            </Link>
          </p>
        )}
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('smsSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.accountSid || !creds.authToken || !creds.phoneNumber}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('smsTestConnection')}
        </Button>
      </div>
    </div>
  );
}
