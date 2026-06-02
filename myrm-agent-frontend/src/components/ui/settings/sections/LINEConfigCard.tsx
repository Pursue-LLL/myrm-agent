'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { LINECredentials } from '@/services/channels';
import { getLINECredentials, saveLINECredentials, testLINEConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: LINECredentials = { channelAccessToken: '', channelSecret: '' };

export function LINEConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<LINECredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['channelAccessToken'],
      getCreds: getLINECredentials,
      saveCreds: saveLINECredentials,
      testConnection: (c) => testLINEConnection(c.channelAccessToken),
      i18nPrefix: 'line',
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

      <div className="space-y-2 max-w-md">
        <Label htmlFor="line-access-token">{t('lineChannelAccessToken')}</Label>
        <div className="relative">
          <Input
            id="line-access-token"
            type={showSecret ? 'text' : 'password'}
            placeholder="••••••••"
            value={creds.channelAccessToken}
            onChange={(e) => handleChange('channelAccessToken', e.target.value)}
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
        <Label htmlFor="line-channel-secret">{t('lineChannelSecret')}</Label>
        <Input
          id="line-channel-secret"
          type="password"
          placeholder="••••••••"
          value={creds.channelSecret}
          onChange={(e) => handleChange('channelSecret', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('lineChannelSecretHint')}</p>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('lineSave')}
        </Button>
        <Button variant="outline" onClick={handleTest} disabled={testing || !creds.channelAccessToken} size="sm">
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('lineTestConnection')}
        </Button>
      </div>
    </div>
  );
}
