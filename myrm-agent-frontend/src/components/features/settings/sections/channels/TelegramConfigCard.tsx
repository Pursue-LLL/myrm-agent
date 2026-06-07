'use client';

import { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconPlus, IconTrash, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import type { BotCommand, TelegramCredentials } from '@/services/channels';
import { getTelegramCredentials, saveTelegramCredentials, testTelegramConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: TelegramCredentials = {
  botToken: '',
  commands: [],
  webhookUrl: '',
  botPolicy: 'deny',
  autoTopic: false,
  notificationsMode: 'important',
  guestMode: false,
};
const CMD_PATTERN = /^[a-z0-9_]{1,32}$/;

function validateCommand(cmd: BotCommand): { command?: string; description?: string } {
  const errors: { command?: string; description?: string } = {};
  if (cmd.command && !CMD_PATTERN.test(cmd.command)) errors.command = 'telegramCommandFormatError';
  if (cmd.command && !cmd.description.trim()) errors.description = 'telegramCommandDescRequired';
  return errors;
}

export function TelegramConfigCard() {
  const t = useTranslations('channels');
  const [showToken, setShowToken] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<TelegramCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['botToken'],
      getCreds: getTelegramCredentials,
      saveCreds: saveTelegramCredentials,
      testConnection: (c) => testTelegramConnection(c.botToken),
      i18nPrefix: 'telegram',
    });

  const commands = creds.commands ?? [];

  const commandErrors = useMemo(() => commands.map(validateCommand), [commands]);

  const hasCommandErrors = useMemo(() => commandErrors.some((e) => e.command || e.description), [commandErrors]);

  const addCommand = useCallback(() => {
    handleChange('commands', [...commands, { command: '', description: '' }]);
  }, [commands, handleChange]);

  const removeCommand = useCallback(
    (index: number) => {
      handleChange(
        'commands',
        commands.filter((_, i) => i !== index),
      );
    },
    [commands, handleChange],
  );

  const updateCommand = useCallback(
    (index: number, field: keyof BotCommand, value: string) => {
      const updated = commands.map((cmd, i) => (i === index ? { ...cmd, [field]: value } : cmd));
      handleChange('commands', updated);
    },
    [commands, handleChange],
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
        <Label htmlFor="telegram-bot-token">{t('telegramBotToken')}</Label>
        <div className="relative">
          <Input
            id="telegram-bot-token"
            type={showToken ? 'text' : 'password'}
            placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
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
      </div>

      <div className="space-y-2">
        <Label htmlFor="telegram-webhook-url">{t('telegramWebhookUrl')}</Label>
        <Input
          id="telegram-webhook-url"
          type="url"
          placeholder="https://your-domain.com/channels/telegram/webhook"
          value={creds.webhookUrl ?? ''}
          onChange={(e) => handleChange('webhookUrl', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('telegramWebhookHint')}</p>
        {creds.webhookUrl && !creds.webhookUrl.startsWith('https://') && (
          <p className="text-xs text-destructive">{t('telegramWebhookHttpsRequired')}</p>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>{t('telegramBotCommands')}</Label>
          <Button variant="ghost" size="sm" onClick={addCommand} className="h-7 gap-1 px-2 text-xs">
            <IconPlus className="h-3 w-3" />
            {t('telegramAddCommand')}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{t('telegramCommandsHint')}</p>
        {commands.map((cmd, i) => {
          const err = commandErrors[i];
          return (
            <div key={i} className="space-y-1">
              <div className="flex items-center gap-2">
                <Input
                  placeholder="/start"
                  value={cmd.command}
                  onChange={(e) => updateCommand(i, 'command', e.target.value)}
                  className={`w-32 font-mono text-sm ${err?.command ? 'border-destructive' : ''}`}
                />
                <Input
                  placeholder={t('telegramCommandDescPlaceholder')}
                  value={cmd.description}
                  onChange={(e) => updateCommand(i, 'description', e.target.value)}
                  className={`flex-1 text-sm ${err?.description ? 'border-destructive' : ''}`}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeCommand(i)}
                  className="h-8 w-8 shrink-0 p-0 text-muted-foreground hover:text-destructive"
                >
                  <IconTrash className="h-3.5 w-3.5" />
                </Button>
              </div>
              {(err?.command || err?.description) && (
                <p className="text-xs text-destructive pl-1">{err.command ? t(err.command) : t(err.description!)}</p>
              )}
            </div>
          );
        })}
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

      <div className="flex items-center justify-between rounded-lg border p-3">
        <div className="space-y-0.5">
          <Label htmlFor="telegram-auto-topic">{t('telegramAutoTopic')}</Label>
          <p className="text-xs text-muted-foreground">{t('telegramAutoTopicHint')}</p>
        </div>
        <Switch
          id="telegram-auto-topic"
          checked={creds.autoTopic ?? false}
          onCheckedChange={(v) => handleChange('autoTopic', v)}
        />
      </div>

      <div className="space-y-2">
        <Label>{t('telegramNotificationsMode')}</Label>
        <Select
          value={creds.notificationsMode ?? 'important'}
          onValueChange={(v: 'important' | 'all') => handleChange('notificationsMode', v)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="important">{t('telegramNotificationsImportant')}</SelectItem>
            <SelectItem value="all">{t('telegramNotificationsAll')}</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">{t('telegramNotificationsHint')}</p>
      </div>

      <div className="flex items-center justify-between rounded-lg border p-3">
        <div className="space-y-0.5">
          <Label htmlFor="telegram-guest-mode">{t('telegramGuestMode')}</Label>
          <p className="text-xs text-muted-foreground">{t('telegramGuestModeHint')}</p>
        </div>
        <Switch
          id="telegram-guest-mode"
          checked={creds.guestMode ?? false}
          onCheckedChange={(v) => handleChange('guestMode', v)}
        />
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || hasCommandErrors || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('telegramSave')}
        </Button>
        <Button variant="outline" onClick={handleTest} disabled={testing || !creds.botToken} size="sm">
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('telegramTestConnection')}
        </Button>
      </div>
    </div>
  );
}
