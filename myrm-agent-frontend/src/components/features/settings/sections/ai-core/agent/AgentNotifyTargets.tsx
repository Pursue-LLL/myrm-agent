'use client';

import { memo, useState, useCallback, useEffect, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Trash2, Bell } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { listChannelStatuses, listPairings, type ChannelPairing } from '@/services/channels';
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

const MANUAL_RECIPIENT_VALUE = '__manual__';

interface AgentNotifyTargetsProps {
  targets: NotifyTarget[];
  onChange: (targets: NotifyTarget[]) => void;
  readonly?: boolean;
}

function pairingLabel(pairing: ChannelPairing): string {
  const name = pairing.display_name?.trim();
  if (name) {
    return `${name} (${pairing.sender_id})`;
  }
  return pairing.sender_id;
}

export const AgentNotifyTargets = memo(function AgentNotifyTargets({
  targets,
  onChange,
  readonly = false,
}: AgentNotifyTargetsProps) {
  const t = useTranslations('agent');
  const [connectedChannels, setConnectedChannels] = useState<string[]>([]);
  const [pairings, setPairings] = useState<ChannelPairing[]>([]);
  const [manualRecipientRows, setManualRecipientRows] = useState<Record<number, boolean>>({});

  useEffect(() => {
    listChannelStatuses()
      .then((statuses) => setConnectedChannels(statuses.filter((s) => s.status === 'running').map((s) => s.name)))
      .catch(() => setConnectedChannels([]));
    listPairings()
      .then(setPairings)
      .catch(() => setPairings([]));
  }, []);

  const activePairings = useMemo(
    () => pairings.filter((p) => p.status === 'active'),
    [pairings],
  );

  const pairingsByChannel = useMemo(() => {
    const map = new Map<string, ChannelPairing[]>();
    for (const pairing of activePairings) {
      const list = map.get(pairing.channel) ?? [];
      list.push(pairing);
      map.set(pairing.channel, list);
    }
    return map;
  }, [activePairings]);

  const availableChannels = CHANNEL_OPTIONS.filter((opt) => connectedChannels.includes(opt.value));

  const handleAdd = useCallback(() => {
    const defaultChannel = availableChannels[0]?.value || 'telegram';
    const channelPairings = pairingsByChannel.get(defaultChannel) ?? [];
    const firstPairing = channelPairings[0];
    const newIndex = targets.length;
    onChange([
      ...targets,
      {
        channel: defaultChannel,
        recipient_id: firstPairing?.sender_id ?? '',
        label: firstPairing?.display_name?.trim() ?? '',
      },
    ]);
    if (!firstPairing) {
      setManualRecipientRows((prev) => ({ ...prev, [newIndex]: true }));
    }
  }, [targets, onChange, availableChannels, pairingsByChannel]);

  const handleRemove = useCallback(
    (idx: number) => {
      onChange(targets.filter((_, i) => i !== idx));
      setManualRecipientRows((prev) => {
        const next: Record<number, boolean> = {};
        for (const [key, value] of Object.entries(prev)) {
          const rowIdx = Number(key);
          if (rowIdx < idx) {
            next[rowIdx] = value;
          } else if (rowIdx > idx) {
            next[rowIdx - 1] = value;
          }
        }
        return next;
      });
    },
    [targets, onChange],
  );

  const handleUpdate = useCallback(
    (idx: number, field: keyof NotifyTarget, value: string) => {
      const updated = targets.map((row, i) => (i === idx ? { ...row, [field]: value } : row));
      onChange(updated);
    },
    [targets, onChange],
  );

  const handleChannelChange = useCallback(
    (idx: number, channel: string) => {
      const channelPairings = pairingsByChannel.get(channel) ?? [];
      const firstPairing = channelPairings[0];
      const updated = targets.map((row, i) =>
        i === idx
          ? {
              ...row,
              channel,
              recipient_id: firstPairing?.sender_id ?? '',
              label: firstPairing?.display_name?.trim() ?? '',
            }
          : row,
      );
      onChange(updated);
      setManualRecipientRows((prev) => ({
        ...prev,
        [idx]: channelPairings.length === 0,
      }));
    },
    [targets, onChange, pairingsByChannel],
  );

  const handlePairingSelect = useCallback(
    (idx: number, value: string) => {
      if (value === MANUAL_RECIPIENT_VALUE) {
        setManualRecipientRows((prev) => ({ ...prev, [idx]: true }));
        return;
      }
      const channelPairings = pairingsByChannel.get(targets[idx]?.channel ?? '') ?? [];
      const pairing = channelPairings.find((p) => p.sender_id === value);
      if (!pairing) {
        return;
      }
      setManualRecipientRows((prev) => ({ ...prev, [idx]: false }));
      const updated = targets.map((row, i) =>
        i === idx
          ? {
              ...row,
              recipient_id: pairing.sender_id,
              label: pairing.display_name?.trim() ?? row.label,
            }
          : row,
      );
      onChange(updated);
    },
    [targets, onChange, pairingsByChannel],
  );

  const showManualRecipient = useCallback(
    (idx: number, channel: string, recipientId: string) => {
      if (manualRecipientRows[idx]) {
        return true;
      }
      const channelPairings = pairingsByChannel.get(channel) ?? [];
      if (channelPairings.length === 0) {
        return true;
      }
      if (recipientId && !channelPairings.some((p) => p.sender_id === recipientId)) {
        return true;
      }
      return false;
    },
    [manualRecipientRows, pairingsByChannel],
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
        {targets.map((target, idx) => {
          const channelPairings = pairingsByChannel.get(target.channel) ?? [];
          const useManual = showManualRecipient(idx, target.channel, target.recipient_id);

          return (
            <div
              key={`${target.channel}-${target.recipient_id}-${idx}`}
              className="flex flex-col sm:flex-row sm:items-center gap-2"
            >
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <Select
                  value={target.channel}
                  onValueChange={(v) => handleChannelChange(idx, v)}
                  disabled={readonly}
                >
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

                {useManual ? (
                  <Input
                    className="h-8 text-xs flex-1 min-w-0 font-mono"
                    placeholder={t('notifyRecipientPlaceholder', { fallback: 'Recipient ID' })}
                    value={target.recipient_id}
                    onChange={(e) => handleUpdate(idx, 'recipient_id', e.target.value)}
                    disabled={readonly}
                  />
                ) : (
                  <Select
                    value={target.recipient_id || undefined}
                    onValueChange={(v) => handlePairingSelect(idx, v)}
                    disabled={readonly}
                  >
                    <SelectTrigger className="h-8 text-xs flex-1 min-w-0">
                      <SelectValue placeholder={t('notifySelectRecipient', { fallback: 'Select recipient' })} />
                    </SelectTrigger>
                    <SelectContent>
                      {channelPairings.map((pairing) => (
                        <SelectItem key={pairing.id} value={pairing.sender_id}>
                          {pairingLabel(pairing)}
                        </SelectItem>
                      ))}
                      <SelectItem value={MANUAL_RECIPIENT_VALUE}>
                        {t('notifyManualRecipient', { fallback: 'Enter ID manually…' })}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                )}
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
          );
        })}

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

        {connectedChannels.length > 0 && activePairings.length === 0 && targets.length === 0 && (
          <p className="text-xs text-muted-foreground italic">
            {t('noPairingsForNotify', {
              fallback: 'Pair a channel contact in Channel settings, or enter a recipient ID manually.',
            })}
          </p>
        )}
      </div>
    </div>
  );
});
