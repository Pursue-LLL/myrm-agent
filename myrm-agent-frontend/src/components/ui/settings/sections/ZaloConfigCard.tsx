'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { ZaloCredentials } from '@/services/channels';
import { getZaloCredentials, saveZaloCredentials, testZaloConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: ZaloCredentials = { accessToken: '' };

export function ZaloConfigCard() {
  const t = useTranslations('channels');
  const [showToken, setShowToken] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<ZaloCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['accessToken'],
      getCreds: getZaloCredentials,
      saveCreds: saveZaloCredentials,
      testConnection: (c) => testZaloConnection(c.accessToken),
      i18nPrefix: 'zalo',
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
        <Label htmlFor="zalo-access-token">{t('zaloAccessToken')}</Label>
        <div className="relative">
          <Input
            id="zalo-access-token"
            type={showToken ? 'text' : 'password'}
            placeholder="••••••••"
            value={creds.accessToken}
            onChange={(e) => handleChange('accessToken', e.target.value)}
            className="pr-10"
          />
          <button
            type="button"
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
            onClick={() => setShowToken(!showToken)}
          >
            {showToken ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('zaloSave')}
        </Button>
        <Button variant="outline" onClick={handleTest} disabled={testing || !creds.accessToken} size="sm">
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('zaloTestConnection')}
        </Button>
      </div>
    </div>
  );
}
