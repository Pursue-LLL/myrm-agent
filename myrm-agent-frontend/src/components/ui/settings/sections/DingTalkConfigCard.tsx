'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { DingTalkCredentials } from '@/services/channels';
import { getDingTalkCredentials, saveDingTalkCredentials, testDingTalkConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: DingTalkCredentials = { clientId: '', clientSecret: '', cardTemplateId: '' };

export function DingTalkConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<DingTalkCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['clientId', 'clientSecret'],
      getCreds: getDingTalkCredentials,
      saveCreds: saveDingTalkCredentials,
      testConnection: (c) => testDingTalkConnection(c.clientId, c.clientSecret),
      i18nPrefix: 'dingtalk',
    });

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

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="dingtalk-client-id">{t('dingtalkClientId')}</Label>
          <Input
            id="dingtalk-client-id"
            placeholder="dingxxxxx"
            value={creds.clientId}
            onChange={(e) => handleChange('clientId', e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="dingtalk-client-secret">{t('dingtalkClientSecret')}</Label>
          <div className="relative">
            <Input
              id="dingtalk-client-secret"
              type={showSecret ? 'text' : 'password'}
              placeholder="••••••••"
              value={creds.clientSecret}
              onChange={(e) => handleChange('clientSecret', e.target.value)}
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
      </div>

      <div className="space-y-2">
        <Label htmlFor="dingtalk-card-template">{t('dingtalkCardTemplateId')}</Label>
        <Input
          id="dingtalk-card-template"
          placeholder={t('dingtalkCardTemplateIdPlaceholder')}
          value={creds.cardTemplateId ?? ''}
          onChange={(e) => handleChange('cardTemplateId', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('dingtalkCardTemplateIdHint')}</p>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('dingtalkSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.clientId || !creds.clientSecret}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('dingtalkTestConnection')}
        </Button>
      </div>
    </div>
  );
}
