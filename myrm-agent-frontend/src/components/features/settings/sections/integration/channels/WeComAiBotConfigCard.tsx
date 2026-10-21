'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import type { WeComAiBotCredentials } from '@/services/channels';
import { getWeComAiBotCredentials, saveWeComAiBotCredentials, testWeComAiBotConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: WeComAiBotCredentials = {
  botId: '',
  secret: '',
};

export function WeComAiBotConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<WeComAiBotCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['botId', 'secret'],
      getCreds: getWeComAiBotCredentials,
      saveCreds: saveWeComAiBotCredentials,
      testConnection: (c) => testWeComAiBotConnection(c.botId, c.secret),
      i18nPrefix: 'wecomAibot',
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

      <p className="text-xs text-muted-foreground">{t('wecomAibotDesc')}</p>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="wecom-aibot-bot-id">{t('wecomAibotBotId')}</Label>
          <Input
            id="wecom-aibot-bot-id"
            placeholder="bot_xxx"
            value={creds.botId}
            onChange={(e) => handleChange('botId', e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="wecom-aibot-secret">{t('wecomAibotSecret')}</Label>
          <div className="relative">
            <Input
              id="wecom-aibot-secret"
              type={showSecret ? 'text' : 'password'}
              placeholder={t('wecomAibotSecretHint')}
              value={creds.secret}
              onChange={(e) => handleChange('secret', e.target.value)}
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

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('wecomAibotSave')}
        </Button>
        <Button variant="outline" onClick={handleTest} disabled={testing || !creds.botId || !creds.secret} size="sm">
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('wecomAibotTestConnection')}
        </Button>
      </div>
    </div>
  );
}
