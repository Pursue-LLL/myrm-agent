'use client';

import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { IconBell } from '@/components/features/icons/PremiumIcons';

import useConfigStore from '@/store/useConfigStore';
import { Switch } from '@/components/primitives/switch';
import { Input } from '@/components/primitives/input';
import { listChannelStatuses } from '@/services/channels';
import type { NotificationDelivery } from '@/services/config/types';

const IM_CHANNELS: Record<string, { label: string; hint: string }> = {
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

const NON_IM = new Set(['chat', 'webhook', 'none', 'web', 'silent']);
const EMPTY_DELIVERIES: NotificationDelivery[] = [];
const WA_SUFFIX = '@s.whatsapp.net';
const toWaTarget = (v: string) => {
  const s = v.trim();
  return s.endsWith(WA_SUFFIX) ? s : `${s}${WA_SUFFIX}`;
};
const fromWaTarget = (t: string) => (t.endsWith(WA_SUFFIX) ? t.slice(0, -WA_SUFFIX.length) : t);

const NotificationChannelEditor = memo(function NotificationChannelEditor() {
  const t = useTranslations('settings');

  const deliveries = useConfigStore((s) => s.personalSettings?.notificationDeliveries ?? EMPTY_DELIVERIES);
  const setDeliveries = useConfigStore((s) => s.setNotificationDeliveries);

  const [connectedChannels, setConnectedChannels] = useState<string[]>([]);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const initializedRef = useRef(false);

  const deliveryMap = new Map<string, string>();
  for (const d of deliveries) {
    deliveryMap.set(d.channel, d.target);
  }

  useEffect(() => {
    listChannelStatuses()
      .then((statuses) =>
        setConnectedChannels(statuses.filter((s) => s.status === 'running' && !NON_IM.has(s.name)).map((s) => s.name)),
      )
      .catch(() => setConnectedChannels([]));
  }, []);

  useEffect(() => {
    if (initializedRef.current || deliveries.length === 0) return;
    initializedRef.current = true;
    const init: Record<string, string> = {};
    for (const d of deliveries) {
      init[d.channel] = d.channel === 'whatsapp' ? fromWaTarget(d.target) : d.target;
    }
    setTargets(init);
  }, [deliveries]);

  const handleToggle = useCallback(
    (ch: string, on: boolean) => {
      if (on) {
        const raw = targets[ch]?.trim();
        if (!raw) return;
        const tgt = ch === 'whatsapp' ? toWaTarget(raw) : raw;
        const next: NotificationDelivery[] = [
          ...deliveries.filter((d) => d.channel !== ch),
          { channel: ch, target: tgt },
        ];
        setDeliveries(next);
      } else {
        const next = deliveries.filter((d) => d.channel !== ch);
        setDeliveries(next.length > 0 ? next : undefined);
      }
    },
    [deliveries, targets, setDeliveries],
  );

  const handleTargetBlur = useCallback(
    (ch: string) => {
      const existing = deliveries.find((d) => d.channel === ch);
      if (!existing) return;
      const raw = targets[ch]?.trim();
      if (!raw) return;
      const tgt = ch === 'whatsapp' ? toWaTarget(raw) : raw;
      if (existing.target !== tgt) {
        const next = deliveries.map((d) => (d.channel === ch ? { ...d, target: tgt } : d));
        setDeliveries(next);
      }
    },
    [deliveries, targets, setDeliveries],
  );

  if (connectedChannels.length === 0) {
    return (
      <div className="p-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-muted rounded-lg">
            <IconBell className="w-[18px] h-[18px] text-black/70 dark:text-white/70" />
          </div>
          <div>
            <p className="text-sm text-black/90 dark:text-white/90 font-medium">{t('notificationChannel')}</p>
            <p className="text-xs text-black/60 dark:text-white/60 mt-0.5">{t('noImChannelsConnected')}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {connectedChannels.map((ch) => {
        const isEnabled = deliveryMap.has(ch);
        const hint = ch === 'whatsapp' ? t('imTargetPlaceholderPhone') : (IM_CHANNELS[ch]?.hint ?? '');

        return (
          <div key={ch} className="p-3 flex items-center gap-3">
            <span className="text-sm font-medium text-black/80 dark:text-white/80 shrink-0 min-w-[80px]">
              {IM_CHANNELS[ch]?.label ?? ch}
            </span>
            <Input
              className="h-8 text-xs flex-1 font-mono"
              placeholder={hint}
              value={targets[ch] ?? ''}
              onChange={(e) => setTargets((prev) => ({ ...prev, [ch]: e.target.value }))}
              onBlur={() => handleTargetBlur(ch)}
            />
            <Switch
              checked={isEnabled}
              onCheckedChange={(on) => handleToggle(ch, on)}
              disabled={!isEnabled && !targets[ch]?.trim()}
            />
          </div>
        );
      })}
    </div>
  );
});

export default NotificationChannelEditor;
