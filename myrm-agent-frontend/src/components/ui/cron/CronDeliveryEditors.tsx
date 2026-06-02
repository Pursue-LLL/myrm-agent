'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, Webhook, MessageSquare, BellOff, Send } from 'lucide-react';
import { WebhookGuide } from './WebhookGuide';
import { EditorToggle } from './EditorToggle';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { toast } from 'sonner';
import type { CronJob } from '@/services/cron';
import { updateCronJob } from '@/services/cron';
import { listChannelStatuses } from '@/services/channels';
import ChannelIcon from '@/components/ui/settings/sections/ChannelIcon';

export interface EditorProps {
  job: CronJob;
  onUpdated: () => void;
}

const BUILTIN_CHANNELS = ['chat', 'webhook', 'none'] as const;
type BuiltinChannel = (typeof BUILTIN_CHANNELS)[number];

const BUILTIN_META: Record<BuiltinChannel, { icon: typeof MessageSquare; labelKey: string }> = {
  chat: { icon: MessageSquare, labelKey: 'deliveryChat' },
  webhook: { icon: Webhook, labelKey: 'deliveryWebhook' },
  none: { icon: BellOff, labelKey: 'deliveryNone' },
};

export const IM_CHANNELS: Record<string, { label: string; hint: string }> = {
  whatsapp: { label: 'WhatsApp', hint: '8613812345678' },
  telegram: { label: 'Telegram', hint: '123456789' },
  feishu: { label: 'Feishu', hint: 'ou_xxxxx' },
  dingtalk: { label: 'DingTalk', hint: 'manager1234' },
  slack: { label: 'Slack', hint: 'C01234567' },
  discord: { label: 'Discord', hint: '123456789012345678' },
  wecom: { label: 'WeCom', hint: 'userid' },
  teams: { label: 'Teams', hint: '19:xxx@thread.tacv2' },
  matrix: { label: 'Matrix', hint: '!roomid:server' },
  googlechat: { label: 'Google Chat', hint: 'spaces/xxx' },
};

const NON_IM_CHANNELS = new Set(['chat', 'webhook', 'none', 'web']);
export const toApiChannel = (ch: string) => (ch === 'none' ? 'silent' : ch);
export const fromApiChannel = (ch: string) => (ch === 'silent' ? 'none' : ch);

const WA_SUFFIX = '@s.whatsapp.net';
const toWaTarget = (v: string) => {
  const s = v.trim();
  return s.endsWith(WA_SUFFIX) ? s : `${s}${WA_SUFFIX}`;
};
const fromWaTarget = (t: string) => (t.endsWith(WA_SUFFIX) ? t.slice(0, -WA_SUFFIX.length) : t);

function useConnectedChannels() {
  const [channels, setChannels] = useState<string[]>([]);
  useEffect(() => {
    listChannelStatuses()
      .then((statuses) =>
        setChannels(statuses.filter((s) => s.status === 'running' && !NON_IM_CHANNELS.has(s.name)).map((s) => s.name)),
      )
      .catch(() => setChannels([]));
  }, []);
  return channels;
}

const TOGGLE_ITEM_CLASS =
  'gap-1 text-xs h-7 px-2.5 rounded-full border border-border bg-muted/50 data-[state=on]:bg-primary/10 data-[state=on]:text-primary data-[state=on]:border-primary/40';

function ChannelToggleGroup(p: {
  value: string;
  onValueChange: (v: string) => void;
  disabled: boolean;
  builtinChannels: readonly string[];
  connectedChannels: string[];
  t: ReturnType<typeof useTranslations<'cron'>>;
}) {
  const { value, onValueChange, disabled, builtinChannels, connectedChannels, t } = p;
  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(v) => v && onValueChange(v)}
      className="flex-wrap justify-start"
      size="sm"
    >
      {builtinChannels.map((ch) => {
        const meta = BUILTIN_META[ch as BuiltinChannel];
        const Icon = meta?.icon ?? MessageSquare;
        const label = meta ? t(meta.labelKey) : ch;
        return (
          <ToggleGroupItem key={ch} value={ch} disabled={disabled} className={TOGGLE_ITEM_CLASS}>
            <Icon className="h-3 w-3" />
            {label}
          </ToggleGroupItem>
        );
      })}
      {connectedChannels.map((ch) => (
        <ToggleGroupItem key={ch} value={ch} disabled={disabled} className={TOGGLE_ITEM_CLASS}>
          <ChannelIcon channelId={ch} size={12} />
          {IM_CHANNELS[ch]?.label ?? ch}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

export function DeliveryEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const connectedChannels = useConnectedChannels();
  const serverChannel = fromApiChannel(job.delivery?.channel ?? 'chat');
  const rawTarget = job.delivery?.target ?? '';
  const [localChannel, setLocalChannel] = useState(serverChannel);
  const [webhookUrl, setWebhookUrl] = useState(rawTarget);
  const [imTarget, setImTarget] = useState(serverChannel === 'whatsapp' ? fromWaTarget(rawTarget) : rawTarget);
  const [saving, setSaving] = useState(false);

  const isImChannel = useMemo(() => !(['chat', 'webhook', 'none'] as string[]).includes(localChannel), [localChannel]);

  useEffect(() => {
    setLocalChannel(serverChannel);
    setWebhookUrl(rawTarget);
    setImTarget(serverChannel === 'whatsapp' ? fromWaTarget(rawTarget) : rawTarget);
  }, [serverChannel, rawTarget]);

  const handleChannelChange = async (ch: string) => {
    if (ch === localChannel) return;
    setLocalChannel(ch);
    if (ch === 'webhook' || ch in IM_CHANNELS) return;
    setSaving(true);
    try {
      await updateCronJob(job.id, { delivery: { channel: toApiChannel(ch) } });
      onUpdated();
      toast.success(t('deliveryUpdated'));
    } catch {
      toast.error(t('actionFail'));
      setLocalChannel(serverChannel);
    } finally {
      setSaving(false);
    }
  };

  const handleWebhookSave = async () => {
    const url = webhookUrl.trim();
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      toast.error(t('webhookUrlInvalid'));
      return;
    }
    setSaving(true);
    try {
      await updateCronJob(job.id, { delivery: { channel: 'webhook', target: url } });
      onUpdated();
      toast.success(t('deliveryUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  const imTargetRequired = isImChannel;
  const imTargetEmpty = !imTarget.trim();

  const handleImSave = async () => {
    if (imTargetRequired && imTargetEmpty) return;
    setSaving(true);
    try {
      const finalTarget = localChannel === 'whatsapp' ? toWaTarget(imTarget) : imTarget.trim();
      await updateCronJob(job.id, {
        delivery: { channel: toApiChannel(localChannel), target: finalTarget },
      });
      onUpdated();
      toast.success(t('deliveryUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <span className="text-xs font-medium text-muted-foreground block mb-1">{t('deliveryLabel')}</span>
      <ChannelToggleGroup
        value={localChannel}
        onValueChange={handleChannelChange}
        disabled={saving}
        builtinChannels={BUILTIN_CHANNELS}
        connectedChannels={connectedChannels}
        t={t}
      />
      {localChannel === 'webhook' && (
        <>
          <div className="flex items-center gap-2">
            <Input
              placeholder="https://example.com/webhook"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              className="h-7 text-xs flex-1"
            />
            <Button size="sm" className="h-7 text-xs" onClick={handleWebhookSave} disabled={saving}>
              {t('save')}
            </Button>
          </div>
          {job.delivery?.secret && <WebhookGuide secret={job.delivery.secret} />}
        </>
      )}
      {isImChannel && (
        <div className="flex items-center gap-2">
          <Send className="h-3 w-3 text-muted-foreground shrink-0" />
          <Input
            placeholder={
              localChannel === 'whatsapp'
                ? t('imTargetPlaceholderPhone')
                : t('imTargetPlaceholderRequired', {
                    example: IM_CHANNELS[localChannel]?.hint ?? '',
                  })
            }
            value={imTarget}
            onChange={(e) => setImTarget(e.target.value)}
            className="h-7 text-xs flex-1"
            required
          />
          <Button
            size="sm"
            className="h-7 text-xs"
            onClick={handleImSave}
            disabled={saving || (imTargetRequired && imTargetEmpty)}
          >
            {t('save')}
          </Button>
        </div>
      )}
    </div>
  );
}

export function FailureDeliveryEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const connectedChannels = useConnectedChannels();
  const existing = job.failure_delivery;
  const initCh = fromApiChannel(existing?.channel ?? 'webhook');
  const initTarget = existing?.target ?? '';
  const [enabled, setEnabled] = useState(!!existing);
  const [channel, setChannel] = useState(initCh);
  const [webhookUrl, setWebhookUrl] = useState(initTarget);
  const [imTarget, setImTarget] = useState(initCh === 'whatsapp' ? fromWaTarget(initTarget) : initTarget);
  const [saving, setSaving] = useState(false);

  const isImChannel = useMemo(() => !(['chat', 'webhook'] as string[]).includes(channel), [channel]);

  useEffect(() => {
    setEnabled(!!job.failure_delivery);
    if (job.failure_delivery) {
      const ch = fromApiChannel(job.failure_delivery.channel ?? 'webhook');
      const tgt = job.failure_delivery.target ?? '';
      setChannel(ch);
      setWebhookUrl(tgt);
      setImTarget(ch === 'whatsapp' ? fromWaTarget(tgt) : tgt);
    }
  }, [job.failure_delivery]);

  const handleToggle = async () => {
    if (enabled) {
      setSaving(true);
      try {
        await updateCronJob(job.id, { failure_delivery: null });
        setEnabled(false);
        onUpdated();
        toast.success(t('failureDeliveryCleared'));
      } catch {
        toast.error(t('actionFail'));
      } finally {
        setSaving(false);
      }
    } else {
      setEnabled(true);
    }
  };

  const failImRequired = isImChannel;
  const failImEmpty = !imTarget.trim();

  const handleSave = async () => {
    if (channel === 'webhook') {
      const url = webhookUrl.trim();
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        toast.error(t('webhookUrlInvalid'));
        return;
      }
    }
    if (failImRequired && failImEmpty) return;
    setSaving(true);
    try {
      let payload: { channel: string; target?: string };
      if (channel === 'webhook') {
        payload = { channel: 'webhook', target: webhookUrl.trim() };
      } else if (channel === 'chat') {
        payload = { channel: 'chat' };
      } else {
        const t2 = channel === 'whatsapp' ? toWaTarget(imTarget) : imTarget.trim();
        payload = { channel: toApiChannel(channel), target: t2 };
      }
      await updateCronJob(job.id, { failure_delivery: payload });
      onUpdated();
      toast.success(t('failureDeliveryUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('failureDeliveryLabel')}</span>
        </div>
        <EditorToggle enabled={enabled} onToggle={handleToggle} disabled={saving} />
      </div>
      {enabled && (
        <>
          <p className="text-[11px] text-muted-foreground">{t('failureDeliveryDesc')}</p>
          <ChannelToggleGroup
            value={channel}
            onValueChange={setChannel}
            disabled={saving}
            builtinChannels={['chat', 'webhook']}
            connectedChannels={connectedChannels}
            t={t}
          />
          {channel === 'webhook' && (
            <>
              <div className="flex items-center gap-2">
                <Input
                  placeholder="https://ops-alert.example.com/webhook"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  className="h-7 text-xs flex-1"
                />
              </div>
              {existing?.secret && <WebhookGuide secret={existing.secret} />}
            </>
          )}
          {isImChannel && (
            <div className="flex items-center gap-2">
              <Send className="h-3 w-3 text-muted-foreground shrink-0" />
              <Input
                placeholder={
                  channel === 'whatsapp'
                    ? t('imTargetPlaceholderPhone')
                    : t('imTargetPlaceholderRequired', {
                        example: IM_CHANNELS[channel]?.hint ?? '',
                      })
                }
                value={imTarget}
                onChange={(e) => setImTarget(e.target.value)}
                className="h-7 text-xs flex-1"
                required
              />
            </div>
          )}
          <Button
            size="sm"
            className="h-7 text-xs"
            onClick={handleSave}
            disabled={saving || (failImRequired && failImEmpty)}
          >
            {t('save')}
          </Button>
        </>
      )}
    </div>
  );
}
