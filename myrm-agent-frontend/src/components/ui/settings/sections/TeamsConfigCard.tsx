'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { TeamsCredentials } from '@/services/channels';
import { getTeamsCredentials, saveTeamsCredentials, testTeamsConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: TeamsCredentials = {
  appId: '',
  appPassword: '',
  tenantId: '',
  welcomeText: '',
  promptStarters: '',
};

export function TeamsConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<TeamsCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['appId', 'appPassword'],
      getCreds: getTeamsCredentials,
      saveCreds: saveTeamsCredentials,
      testConnection: (c) => testTeamsConnection(c.appId, c.appPassword, c.tenantId),
      i18nPrefix: 'teams',
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
          <Label htmlFor="teams-app-id">{t('teamsAppId')}</Label>
          <Input
            id="teams-app-id"
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            value={creds.appId}
            onChange={(e) => handleChange('appId', e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="teams-app-password">{t('teamsAppPassword')}</Label>
          <div className="relative">
            <Input
              id="teams-app-password"
              type={showSecret ? 'text' : 'password'}
              placeholder="••••••••"
              value={creds.appPassword}
              onChange={(e) => handleChange('appPassword', e.target.value)}
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
          <Label htmlFor="teams-tenant-id">{t('teamsTenantId')}</Label>
          <Input
            id="teams-tenant-id"
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            value={creds.tenantId}
            onChange={(e) => handleChange('tenantId', e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-4 border-t pt-4">
        <p className="text-sm font-medium text-muted-foreground">{t('teamsWelcomeSection')}</p>
        <div className="space-y-2">
          <Label htmlFor="teams-welcome-text">{t('teamsWelcomeText')}</Label>
          <Textarea
            id="teams-welcome-text"
            placeholder={t('teamsWelcomeTextPlaceholder')}
            value={creds.welcomeText}
            onChange={(e) => handleChange('welcomeText', e.target.value)}
            rows={2}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="teams-prompt-starters">{t('teamsPromptStarters')}</Label>
          <Input
            id="teams-prompt-starters"
            placeholder={t('teamsPromptStartersPlaceholder')}
            value={creds.promptStarters}
            onChange={(e) => handleChange('promptStarters', e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('teamsPromptStartersHint')}</p>
        </div>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('teamsSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.appId || !creds.appPassword}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('teamsTestConnection')}
        </Button>
      </div>
    </div>
  );
}
