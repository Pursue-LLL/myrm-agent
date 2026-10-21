'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import type { IRCCredentials } from '@/services/channels';
import { getIRCCredentials, saveIRCCredentials, testIRCConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: IRCCredentials = {
  server: '',
  port: 6667,
  nick: '',
  channels: '',
  password: '',
  useSsl: false,
};

export function IRCConfigCard() {
  const t = useTranslations('channels');
  const [showPassword, setShowPassword] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<IRCCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['server', 'nick'],
      getCreds: getIRCCredentials,
      saveCreds: saveIRCCredentials,
      testConnection: (c) => testIRCConnection(c.server, c.port, c.nick),
      i18nPrefix: 'irc',
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

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-lg">
        <div className="space-y-2">
          <Label htmlFor="irc-server">{t('ircServer')}</Label>
          <Input
            id="irc-server"
            placeholder="irc.libera.chat"
            value={creds.server}
            onChange={(e) => handleChange('server', e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="irc-port">{t('ircPort')}</Label>
          <Input
            id="irc-port"
            type="number"
            value={creds.port}
            onChange={(e) => handleChange('port', parseInt(e.target.value) || 6667)}
          />
        </div>
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="irc-nick">{t('ircNick')}</Label>
        <Input
          id="irc-nick"
          placeholder="myrm-bot"
          value={creds.nick}
          onChange={(e) => handleChange('nick', e.target.value)}
        />
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="irc-channels">{t('ircChannels')}</Label>
        <Input
          id="irc-channels"
          placeholder="#general, #support"
          value={creds.channels}
          onChange={(e) => handleChange('channels', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('ircChannelsHint')}</p>
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="irc-password">{t('ircPassword')}</Label>
        <div className="relative">
          <Input
            id="irc-password"
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

      <div className="flex items-center gap-2">
        <input
          id="irc-ssl"
          type="checkbox"
          checked={creds.useSsl}
          onChange={(e) => handleChange('useSsl', e.target.checked)}
          className="h-4 w-4 rounded border-border"
        />
        <Label htmlFor="irc-ssl" className="text-sm font-normal">
          {t('ircUseSsl')}
        </Label>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('ircSave')}
        </Button>
        <Button variant="outline" onClick={handleTest} disabled={testing || !creds.server || !creds.nick} size="sm">
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('ircTestConnection')}
        </Button>
      </div>
    </div>
  );
}
