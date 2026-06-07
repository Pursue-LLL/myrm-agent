'use client';

import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { IconLoader, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import type { MattermostCredentials } from '@/services/channels';
import { getMattermostCredentials, saveMattermostCredentials, testMattermostConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: MattermostCredentials = { serverUrl: '', accessToken: '' };

export function MattermostConfigCard() {
  const t = useTranslations('channels');

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<MattermostCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['serverUrl', 'accessToken'],
      getCreds: getMattermostCredentials,
      saveCreds: saveMattermostCredentials,
      testConnection: (c) => testMattermostConnection(c.serverUrl, c.accessToken),
      i18nPrefix: 'mattermost',
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
        <Label htmlFor="mattermost-server-url">{t('mattermostServerUrl')}</Label>
        <Input
          id="mattermost-server-url"
          placeholder="https://mattermost.example.com"
          value={creds.serverUrl}
          onChange={(e) => handleChange('serverUrl', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('mattermostServerUrlHint')}</p>
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="mattermost-access-token">{t('mattermostAccessToken')}</Label>
        <Input
          id="mattermost-access-token"
          type="password"
          value={creds.accessToken}
          onChange={(e) => handleChange('accessToken', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('mattermostAccessTokenHint')}</p>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('mattermostSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.serverUrl || !creds.accessToken}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('mattermostTestConnection')}
        </Button>
      </div>
    </div>
  );
}
