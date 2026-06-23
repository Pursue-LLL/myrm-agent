'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import type { IMessageCredentials } from '@/services/channels';
import { getIMessageCredentials, saveIMessageCredentials, testIMessageConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: IMessageCredentials = { apiUrl: '', password: '', webhookUrl: '' };

export function IMessageConfigCard() {
  const t = useTranslations('channels');
  const [showPassword, setShowPassword] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<IMessageCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['apiUrl', 'password'],
      getCreds: getIMessageCredentials,
      saveCreds: saveIMessageCredentials,
      testConnection: (c) => testIMessageConnection(c.apiUrl, c.password),
      i18nPrefix: 'imessage',
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
        <Label htmlFor="imessage-api-url">{t('imessageApiUrl')}</Label>
        <Input
          id="imessage-api-url"
          placeholder="http://localhost:1234"
          value={creds.apiUrl}
          onChange={(e) => handleChange('apiUrl', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('imessageApiUrlHint')}</p>
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="imessage-password">{t('imessagePassword')}</Label>
        <div className="relative">
          <Input
            id="imessage-password"
            type={showPassword ? 'text' : 'password'}
            placeholder="••••••••"
            value={creds.password}
            onChange={(e) => handleChange('password', e.target.value)}
            className="pr-10"
          />
          <button
            type="button"
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
            onClick={() => setShowPassword(!showPassword)}
          >
            {showPassword ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="imessage-webhook-url">{t('imessageWebhookUrl')}</Label>
        <Input
          id="imessage-webhook-url"
          placeholder="http://your-server:8000/api/channels/imessage/webhook"
          value={creds.webhookUrl ?? ''}
          onChange={(e) => handleChange('webhookUrl', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('imessageWebhookUrlHint')}</p>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('imessageSave')}
        </Button>
        <Button variant="outline" onClick={handleTest} disabled={testing || !creds.apiUrl || !creds.password} size="sm">
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('imessageTestConnection')}
        </Button>
      </div>
    </div>
  );
}
