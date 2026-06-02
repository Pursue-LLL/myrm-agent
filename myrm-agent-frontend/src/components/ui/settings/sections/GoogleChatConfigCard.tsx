'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Label } from '@/components/ui/label';
import type { GoogleChatCredentials } from '@/services/channels';
import { getGoogleChatCredentials, saveGoogleChatCredentials, testGoogleChatConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: GoogleChatCredentials = { serviceAccountJson: '' };

export function GoogleChatConfigCard() {
  const t = useTranslations('channels');
  const [jsonError, setJsonError] = useState('');

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<GoogleChatCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['serviceAccountJson'],
      getCreds: getGoogleChatCredentials,
      saveCreds: saveGoogleChatCredentials,
      testConnection: (c) => testGoogleChatConnection(c.serviceAccountJson),
      i18nPrefix: 'googlechat',
    });

  const handleJsonChange = useCallback(
    (value: string) => {
      handleChange('serviceAccountJson', value);
      if (value.trim()) {
        try {
          const parsed = JSON.parse(value);
          if (!parsed.client_email || !parsed.private_key) {
            setJsonError(t('googlechatJsonMissingFields'));
          } else {
            setJsonError('');
          }
        } catch {
          setJsonError(t('googlechatJsonInvalid'));
        }
      } else {
        setJsonError('');
      }
    },
    [handleChange, t],
  );

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

      <div className="space-y-2">
        <Label htmlFor="googlechat-sa-json">{t('googlechatServiceAccount')}</Label>
        <textarea
          id="googlechat-sa-json"
          className="flex min-h-[120px] w-full rounded-full border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 font-mono"
          placeholder={t('googlechatServiceAccountPlaceholder')}
          value={creds.serviceAccountJson}
          onChange={(e) => handleJsonChange(e.target.value)}
          rows={6}
        />
        {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !!jsonError || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('googlechatSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.serviceAccountJson || !!jsonError}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('googlechatTestConnection')}
        </Button>
      </div>
    </div>
  );
}
