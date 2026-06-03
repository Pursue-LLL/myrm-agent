'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Trash2, Bell } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { listChannelStatuses } from '@/services/channels';
import type { NotifyTarget } from '@/services/agent';

const CHANNEL_OPTIONS = [
  { value: 'telegram', label: 'Telegram' },
  { value: 'slack', label: 'Slack' },
  { value: 'discord', label: 'Discord' },
  { value: 'feishu', label: 'Feishu' },
  { value: 'dingtalk', label: 'DingTalk' },
  { value: 'wecom', label: 'WeCom' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'teams', label: 'Teams' },
  { value: 'matrix', label: 'Matrix' },
  { value: 'email', label: 'Email' },
] as const;

interface AgentNotifyTargetsProps {
  targets: NotifyTarget[];
  onChange: (targets: NotifyTarget[]) => void;
  readonly?: boolean;
}

export const AgentNotifyTargets = memo(function AgentNotifyTargets({
  targets,
  onChange,
  readonly = false,
}: AgentNotifyTargetsProps) {
  const t = useTranslations('agent');
  const [connectedChannels, setConnectedChannels] = useState<string[]>([]);

  useEffect(() => {
    listChannelStatuses()
      .then((statuses) => setConnectedChannels(statuses.filter((s) => s.status === 'running').map((s) => s.name)))
      .catch(() => setConnectedChannels([]));
  }, []);

  const availableChannels = CHANNEL_OPTIONS.filter((opt) => connectedChannels.includes(opt.value));

  const handleAdd = useCallback(() => {
    const defaultChannel = availableChannels[0]?.value || 'telegram';
    onChange([...targets, { channel: defaultChannel, recipient_id: '', label: '' }]);
  }, [targets, onChange, availableChannels]);

  const handleRemove = useCallback(
    (idx: number) => {
      onChange(targets.filter((_, i) => i !== idx));
    },
    [targets, onChange],
  );

  const handleUpdate = useCallback(
    (idx: number, field: keyof NotifyTarget, value: string) => {
      const updated = targets.map((t, i) => (i === idx ? { ...t, [field]: value } : t));
      onChange(updated);
    },
    [targets, onChange],
  );

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium text-foreground">
            {t('notifyTargets', { fallback: 'Notification Channels' })}
          </h3>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">
          {t('notifyTargetsDesc', {
            fallback: 'Allow this agent to send notifications to your connected channels.',
          })}
        </p>
      </div>

      <div className="space-y-2">
        {targets.map((target, idx) => (
          <div key={idx} className="flex flex-col sm:flex-row sm:items-center gap-2">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <Select value={target.channel} onValueChange={(v) => handleUpdate(idx, 'channel', v)} disabled={readonly}>
                <SelectTrigger className="w-[120px] h-8 text-xs shrink-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(availableChannels.length > 0 ? availableChannels : CHANNEL_OPTIONS).map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                className="h-8 text-xs flex-1 min-w-0 font-mono"
                placeholder={t('notifyRecipientPlaceholder', { fallback: 'Recipient ID' })}
                value={target.recipient_id}
                onChange={(e) => handleUpdate(idx, 'recipient_id', e.target.value)}
                disabled={readonly}
              />
            </div>
            <div className="flex items-center gap-2">
              <Input
                className="h-8 text-xs w-full sm:w-[100px]"
                placeholder={t('notifyLabelPlaceholder', { fallback: 'Label' })}
                value={target.label || ''}
                onChange={(e) => handleUpdate(idx, 'label', e.target.value)}
                disabled={readonly}
              />
              {!readonly && (
                <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => handleRemove(idx)}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              )}
            </div>
          </div>
        ))}

        {!readonly && (
          <Button
            variant="outline"
            size="sm"
            className="w-full h-8 text-xs"
            onClick={handleAdd}
            disabled={availableChannels.length === 0 && connectedChannels.length === 0}
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            {t('addNotifyTarget', { fallback: 'Add Notification Target' })}
          </Button>
        )}

        {connectedChannels.length === 0 && targets.length === 0 && (
          <p className="text-xs text-muted-foreground italic">
            {t('noChannelsForNotify', {
              fallback: 'Connect a channel in settings to enable notifications.',
            })}
          </p>
        )}
      </div>
    </div>
  );
});
