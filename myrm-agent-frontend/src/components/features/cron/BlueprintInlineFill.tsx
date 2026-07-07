'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { ArrowLeft, Loader2, MessageCircle, Send, Sparkles } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/primitives/toggle-group';
import { toast } from 'sonner';
import useCronStore from '@/store/useCronStore';
import useConfigStore from '@/store/useConfigStore';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';
import { buildBlueprintCreatePayload, humanizeSchedule, type CronBlueprint } from './cron-blueprints';
import { IM_CHANNELS, toApiChannel } from './CronDeliveryEditors';
import { listChannelStatuses } from '@/services/channels';
import ChannelIcon from '@/components/features/settings/sections/integration/channels/ChannelIcon';

interface BlueprintInlineFillProps {
  blueprint: CronBlueprint;
  onBack: () => void;
  onCreated: () => void;
}

const TOGGLE_CLS = 'gap-1.5 text-xs h-8 px-3 rounded-full border border-border bg-muted/50 data-[state=on]:bg-primary/10 data-[state=on]:text-primary data-[state=on]:border-primary/40';

export default function BlueprintInlineFill({ blueprint, onBack, onCreated }: BlueprintInlineFillProps) {
  const t = useTranslations('cron');
  const locale = useLocale();
  const { createJob } = useCronStore();
  const userTz = useConfigStore((s) => s.personalSettings?.timezone) || getBrowserTimezone();
  const displayTitle = blueprint.title?.[locale] || t(blueprint.titleKey);
  const displayDesc = blueprint.description?.[locale] || t(blueprint.descKey);
  const [slotValues, setSlotValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [deliveryChannel, setDeliveryChannel] = useState<string>('chat');
  const [deliveryTarget, setDeliveryTarget] = useState('');
  const [connectedChannels, setConnectedChannels] = useState<string[]>([]);

  useEffect(() => {
    const NON_IM = new Set(['chat', 'webhook', 'none', 'web']);
    listChannelStatuses().then((statuses) => {
      setConnectedChannels(
        statuses
          .filter((s) => s.status === 'running' && !NON_IM.has(s.name))
          .map((s) => s.name),
      );
    }).catch(() => {});
  }, []);

  const getVal = (name: string, fallback: string) => slotValues[name] ?? fallback;
  const setVal = (name: string, val: string) => setSlotValues((prev) => ({ ...prev, [name]: val }));

  const previewSchedule = blueprint.buildSchedule(
    Object.fromEntries(blueprint.slots.map((s) => [s.name, slotValues[s.name] ?? s.default])),
  );

  const handleSubmit = async () => {
    setSaving(true);
    try {
      const merged = Object.fromEntries(
        blueprint.slots.map((s) => [s.name, slotValues[s.name] ?? s.default]),
      );
      const delivery = deliveryChannel !== 'chat'
        ? { channel: toApiChannel(deliveryChannel), ...(deliveryTarget.trim() ? { target: deliveryTarget.trim() } : {}) }
        : undefined;
      const payload = await buildBlueprintCreatePayload(
        blueprint,
        merged,
        userTz,
        locale,
        t,
        delivery,
      );
      await createJob(payload);
      toast.success(t('createSuccess'));
      onCreated();
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-3 w-3" />
        {t('blueprint.backToTemplates')}
      </button>

      <div className="flex items-center gap-2">
        <blueprint.icon className="h-5 w-5 text-primary" />
        <span className="text-sm font-medium">{displayTitle}</span>
      </div>
      <p className="text-xs text-muted-foreground">{displayDesc}</p>

      {blueprint.slots.map((slot) => (
        <div key={slot.name} className="space-y-1.5">
          <Label className="text-xs">{t(slot.label)}</Label>
          {slot.type === 'time' && (
            <Input
              type="time"
              value={getVal(slot.name, slot.default)}
              onChange={(e) => setVal(slot.name, e.target.value)}
              className="h-8 text-sm w-32"
            />
          )}
          {slot.type === 'text' && (
            <Input
              value={getVal(slot.name, slot.default)}
              onChange={(e) => setVal(slot.name, e.target.value)}
              placeholder={slot.default || t('blueprint.slotTextPlaceholder')}
              className="h-8 text-sm"
            />
          )}
          {slot.type === 'enum' && slot.name === 'day' && (
            <Select value={getVal(slot.name, slot.default)} onValueChange={(v) => setVal(slot.name, v)}>
              <SelectTrigger className="h-8 text-sm w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {['1', '2', '3', '4', '5', '6', '0'].map((d) => (
                  <SelectItem key={d} value={d}>
                    {t(`blueprint.day${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][Number(d)]}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {slot.type === 'enum' && slot.name !== 'day' && slot.options && (
            <Select value={getVal(slot.name, slot.default)} onValueChange={(v) => setVal(slot.name, v)}>
              <SelectTrigger className="h-8 text-sm w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {slot.options.map((opt) => (
                  <SelectItem key={opt} value={opt}>
                    {t(`blueprint.enum.${opt}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      ))}

      <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
        <p className="text-xs text-muted-foreground">
          <Sparkles className="h-3 w-3 inline mr-1" />
          {humanizeSchedule(previewSchedule)}
        </p>
      </div>

      {connectedChannels.length > 0 && (
        <div className="space-y-1.5">
          <Label className="text-xs">{t('deliveryLabel')}</Label>
          <ToggleGroup
            type="single"
            value={deliveryChannel}
            onValueChange={(v) => v && setDeliveryChannel(v)}
            className="flex-wrap justify-start"
            size="sm"
          >
            <ToggleGroupItem value="chat" className={TOGGLE_CLS}>
              <MessageCircle className="h-3.5 w-3.5" />
              {t('deliveryChat')}
            </ToggleGroupItem>
            {connectedChannels.map((ch) => (
              <ToggleGroupItem key={ch} value={ch} className={TOGGLE_CLS}>
                <ChannelIcon channelId={ch} size={14} />
                {IM_CHANNELS[ch]?.label ?? ch}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {(deliveryChannel in IM_CHANNELS) && (
            <div className="flex items-center gap-2">
              <Send className="h-3 w-3 text-muted-foreground shrink-0" />
              <Input
                placeholder={IM_CHANNELS[deliveryChannel]?.hint ?? ''}
                value={deliveryTarget}
                onChange={(e) => setDeliveryTarget(e.target.value)}
                className="h-7 text-xs flex-1"
              />
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="ghost" size="sm" onClick={onBack} disabled={saving}>
          {t('cancel')}
        </Button>
        <Button size="sm" onClick={handleSubmit} disabled={saving} className="gap-1.5">
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {t('createSubmit')}
        </Button>
      </div>
    </div>
  );
}
