'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import type { DiscordCredentials } from '@/services/channels';
import { getDiscordCredentials, saveDiscordCredentials, testDiscordConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: DiscordCredentials = {
  botToken: '',
  botPolicy: 'deny',
  autoThread: true,
  noThreadChannels: '',
  voiceEnabled: false,
  voiceBargeInEnabled: false,
  voiceWakeWords: '',
  voiceTimeout: 300,
  voiceAutoJoinChannel: '',
  voiceTextChannel: '',
  voiceFollowUsers: '',
  voiceAllowedChannels: '',
};

export function DiscordConfigCard() {
  const t = useTranslations('channels');
  const [showToken, setShowToken] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<DiscordCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['botToken'],
      getCreds: getDiscordCredentials,
      saveCreds: saveDiscordCredentials,
      testConnection: (c) => testDiscordConnection(c.botToken),
      i18nPrefix: 'discord',
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

      <div className="space-y-2">
        <Label htmlFor="discord-bot-token">{t('discordBotToken')}</Label>
        <div className="relative">
          <Input
            id="discord-bot-token"
            type={showToken ? 'text' : 'password'}
            placeholder="your-discord-bot-token"
            value={creds.botToken}
            onChange={(e) => handleChange('botToken', e.target.value)}
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
        <p className="text-xs text-muted-foreground">{t('discordBotTokenHint')}</p>
      </div>

      <div className="space-y-2">
        <Label>{t('feishuBotPolicy')}</Label>
        <Select
          value={creds.botPolicy}
          onValueChange={(v: 'deny' | 'mention_only' | 'allow') => handleChange('botPolicy', v)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="deny">{t('feishuBotPolicyDeny')}</SelectItem>
            <SelectItem value="mention_only">{t('feishuBotPolicyMentionOnly')}</SelectItem>
            <SelectItem value="allow">{t('feishuBotPolicyAllow')}</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">{t('feishuBotPolicyHint')}</p>
      </div>

      {/* Auto-Thread Settings */}
      <div className="space-y-3 rounded-full border border-border/50 p-3">
        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="discord-auto-thread">{t('discordAutoThread')}</Label>
            <p className="text-xs text-muted-foreground">{t('discordAutoThreadHint')}</p>
          </div>
          <Switch
            id="discord-auto-thread"
            checked={creds.autoThread ?? true}
            onCheckedChange={(v) => handleChange('autoThread', v)}
          />
        </div>

        {creds.autoThread !== false && (
          <div className="space-y-2">
            <Label htmlFor="discord-no-thread-channels">{t('discordNoThreadChannels')}</Label>
            <Input
              id="discord-no-thread-channels"
              placeholder="123456789012345678, 987654321098765432"
              value={creds.noThreadChannels ?? ''}
              onChange={(e) => handleChange('noThreadChannels', e.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t('discordNoThreadChannelsHint')}</p>
          </div>
        )}
      </div>

      {/* Voice Channel Settings */}
      <div className="space-y-3 rounded-full border border-border/50 p-3">
        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="discord-voice-enabled">{t('discordVoiceEnabled')}</Label>
            <p className="text-xs text-muted-foreground">{t('discordVoiceEnabledHint')}</p>
          </div>
          <Switch
            id="discord-voice-enabled"
            checked={creds.voiceEnabled ?? false}
            onCheckedChange={(v) => handleChange('voiceEnabled', v)}
          />
        </div>

        {creds.voiceEnabled && (
          <>
            <div className="flex items-center justify-between pt-2">
              <div>
                <Label htmlFor="discord-voice-barge-in">{t('discordVoiceBargeInEnabled')}</Label>
                <p className="text-xs text-muted-foreground">{t('discordVoiceBargeInHint')}</p>
              </div>
              <Switch
                id="discord-voice-barge-in"
                checked={creds.voiceBargeInEnabled ?? false}
                onCheckedChange={(v) => handleChange('voiceBargeInEnabled', v)}
              />
            </div>

            <div className="space-y-2 pt-2">
              <Label htmlFor="discord-voice-wake-words">{t('discordVoiceWakeWords')}</Label>
              <Input
                id="discord-voice-wake-words"
                placeholder="myrm, bot, assistant"
                value={creds.voiceWakeWords ?? ''}
                onChange={(e) => handleChange('voiceWakeWords', e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t('discordVoiceWakeWordsHint')}</p>
            </div>

            <div className="space-y-2 pt-2">
              <Label htmlFor="discord-voice-timeout">{t('discordVoiceTimeout')}</Label>
              <Input
                id="discord-voice-timeout"
                type="number"
                min={0}
                max={3600}
                value={creds.voiceTimeout ?? 300}
                onChange={(e) => handleChange('voiceTimeout', parseInt(e.target.value, 10) || 300)}
                className="w-32"
              />
              <p className="text-xs text-muted-foreground">{t('discordVoiceTimeoutHint')}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="discord-voice-auto-join">{t('discordVoiceAutoJoin')}</Label>
              <Input
                id="discord-voice-auto-join"
                placeholder="123456789012345678"
                value={creds.voiceAutoJoinChannel ?? ''}
                onChange={(e) => handleChange('voiceAutoJoinChannel', e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t('discordVoiceAutoJoinHint')}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="discord-voice-text-channel">{t('discordVoiceTextChannel')}</Label>
              <Input
                id="discord-voice-text-channel"
                placeholder="123456789012345678"
                value={creds.voiceTextChannel ?? ''}
                onChange={(e) => handleChange('voiceTextChannel', e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t('discordVoiceTextChannelHint')}</p>
            </div>

            <div className="space-y-2 pt-2">
              <Label htmlFor="discord-voice-follow-users">{t('discordVoiceFollowUsers')}</Label>
              <Input
                id="discord-voice-follow-users"
                placeholder="123456789012345678, 987654321098765432"
                value={creds.voiceFollowUsers ?? ''}
                onChange={(e) => handleChange('voiceFollowUsers', e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t('discordVoiceFollowUsersHint')}</p>
            </div>

            <div className="space-y-2 pt-2">
              <Label htmlFor="discord-voice-allowed-channels">{t('discordVoiceAllowedChannels')}</Label>
              <Input
                id="discord-voice-allowed-channels"
                placeholder="guild_id:channel_id, guild_id:channel_id"
                value={creds.voiceAllowedChannels ?? ''}
                onChange={(e) => handleChange('voiceAllowedChannels', e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t('discordVoiceAllowedChannelsHint')}</p>
            </div>
          </>
        )}
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('discordSave')}
        </Button>
        <Button variant="outline" onClick={handleTest} disabled={testing || !creds.botToken} size="sm">
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('discordTestConnection')}
        </Button>
      </div>
    </div>
  );
}
