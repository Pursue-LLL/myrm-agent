'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import { isSandbox } from '@/lib/deploy-mode';
import type { SlackCredentials } from '@/services/channels';
import { getSlackCredentials, saveSlackCredentials, testSlackConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { CpInboundUrlBanner } from './CpInboundUrlBanner';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: SlackCredentials = { botToken: '', appToken: '', signingSecret: '', replyInThread: true };

export function SlackConfigCard() {
  const t = useTranslations('channels');
  const sandbox = isSandbox();
  const [showSecret, setShowSecret] = useState(false);

  const requiredFields: (keyof SlackCredentials)[] = sandbox
    ? ['botToken', 'signingSecret']
    : ['botToken', 'appToken'];

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<SlackCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields,
      getCreds: getSlackCredentials,
      saveCreds: saveSlackCredentials,
      testConnection: (c) => testSlackConnection(c.botToken, c.appToken),
      i18nPrefix: 'slack',
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
          <Label htmlFor="slack-bot-token">{t('slackBotToken')}</Label>
          <div className="relative">
            <Input
              id="slack-bot-token"
              type={showSecret ? 'text' : 'password'}
              placeholder="xoxb-..."
              value={creds.botToken}
              onChange={(e) => handleChange('botToken', e.target.value)}
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
          <Label htmlFor="slack-app-token">{t('slackAppToken')}</Label>
          <Input
            id="slack-app-token"
            type={showSecret ? 'text' : 'password'}
            placeholder="xapp-..."
            value={creds.appToken}
            onChange={(e) => handleChange('appToken', e.target.value)}
          />
        </div>

        {sandbox && (
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="slack-signing-secret">{t('slackSigningSecret')}</Label>
            <Input
              id="slack-signing-secret"
              type={showSecret ? 'text' : 'password'}
              placeholder="..."
              value={creds.signingSecret ?? ''}
              onChange={(e) => handleChange('signingSecret', e.target.value)}
            />
          </div>
        )}
      </div>

      {sandbox && <CpInboundUrlBanner channel="slack" />}

      <div className="flex items-center gap-3">
        <Switch
          id="slack-reply-thread"
          checked={creds.replyInThread}
          onCheckedChange={(v) => handleChange('replyInThread', v)}
        />
        <div>
          <Label htmlFor="slack-reply-thread">{t('slackReplyInThread')}</Label>
          <p className="text-xs text-muted-foreground">{t('slackReplyInThreadHint')}</p>
        </div>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('slackSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.botToken || !creds.appToken}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('slackTestConnection')}
        </Button>
      </div>
    </div>
  );
}
