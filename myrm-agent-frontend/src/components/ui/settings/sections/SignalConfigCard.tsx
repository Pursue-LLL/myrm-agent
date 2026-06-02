'use client';

import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { SignalCredentials } from '@/services/channels';
import { getSignalCredentials, saveSignalCredentials, testSignalConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: SignalCredentials = { apiUrl: '', phoneNumber: '' };

export function SignalConfigCard() {
  const t = useTranslations('channels');

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<SignalCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['apiUrl', 'phoneNumber'],
      getCreds: getSignalCredentials,
      saveCreds: saveSignalCredentials,
      testConnection: (c) => testSignalConnection(c.apiUrl, c.phoneNumber),
      i18nPrefix: 'signal',
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
        <Label htmlFor="signal-api-url">{t('signalApiUrl')}</Label>
        <Input
          id="signal-api-url"
          placeholder="http://localhost:8080"
          value={creds.apiUrl}
          onChange={(e) => handleChange('apiUrl', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('signalApiUrlHint')}</p>
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="signal-phone">{t('signalPhoneNumber')}</Label>
        <Input
          id="signal-phone"
          placeholder="+1234567890"
          value={creds.phoneNumber}
          onChange={(e) => handleChange('phoneNumber', e.target.value)}
        />
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('signalSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.apiUrl || !creds.phoneNumber}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('signalTestConnection')}
        </Button>
      </div>
    </div>
  );
}
