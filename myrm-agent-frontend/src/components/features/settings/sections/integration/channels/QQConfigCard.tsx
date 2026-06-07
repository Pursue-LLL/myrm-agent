'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import type { QQCredentials } from '@/services/channels';
import { getQQCredentials, saveQQCredentials, testQQConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: QQCredentials = { appId: '', clientSecret: '' };

export function QQConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<QQCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['appId', 'clientSecret'],
      getCreds: getQQCredentials,
      saveCreds: saveQQCredentials,
      testConnection: (c) => testQQConnection(c.appId, c.clientSecret),
      i18nPrefix: 'qq',
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
        <Label htmlFor="qq-app-id">{t('qqAppId')}</Label>
        <Input
          id="qq-app-id"
          placeholder="102xxxxxx"
          value={creds.appId}
          onChange={(e) => handleChange('appId', e.target.value)}
        />
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="qq-client-secret">{t('qqClientSecret')}</Label>
        <div className="relative">
          <Input
            id="qq-client-secret"
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

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('qqSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.appId || !creds.clientSecret}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('qqTestConnection')}
        </Button>
      </div>
    </div>
  );
}
