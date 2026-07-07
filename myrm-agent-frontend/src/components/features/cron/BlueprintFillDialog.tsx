'use client';

import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Loader2, MessageCircle, Send, Sparkles } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/primitives/toggle-group';
import { toast } from 'sonner';
import useCronStore from '@/store/useCronStore';
import useConfigStore from '@/store/useConfigStore';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';
import { buildJobPayload, humanizeSchedule, type CronBlueprint } from './cron-blueprints';
import { IM_CHANNELS, toApiChannel } from './CronDeliveryEditors';
import { listChannelStatuses } from '@/services/channels';
import ChannelIcon from '@/components/features/settings/sections/integration/channels/ChannelIcon';

const WEEKDAY_OPTIONS: { value: string; labelKey: string }[] = [
  { value: '1', labelKey: 'blueprint.dayMon' },
  { value: '2', labelKey: 'blueprint.dayTue' },
  { value: '3', labelKey: 'blueprint.dayWed' },
  { value: '4', labelKey: 'blueprint.dayThu' },
  { value: '5', labelKey: 'blueprint.dayFri' },
  { value: '6', labelKey: 'blueprint.daySat' },
  { value: '0', labelKey: 'blueprint.daySun' },
];

const TOGGLE_CLS =
  'gap-1.5 text-xs h-8 px-3 rounded-full border border-border bg-muted/50 data-[state=on]:bg-primary/10 data-[state=on]:text-primary data-[state=on]:border-primary/40';

interface BlueprintFillDialogProps {
  blueprint: CronBlueprint | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function BlueprintFillDialog({ blueprint, open, onOpenChange }: BlueprintFillDialogProps) {
  const t = useTranslations('cron');
  const locale = useLocale();
  const { createJob } = useCronStore();
  const userTz = useConfigStore((s) => s.personalSettings?.timezone) || getBrowserTimezone();
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [deliveryChannel, setDeliveryChannel] = useState<string>('chat');
  const [deliveryTarget, setDeliveryTarget] = useState('');
  const [connectedChannels, setConnectedChannels] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      const NON_IM = new Set(['chat', 'webhook', 'none', 'web']);
      listChannelStatuses()
        .then((statuses) =>
          setConnectedChannels(
            statuses.filter((s) => s.status === 'running' && !NON_IM.has(s.name)).map((s) => s.name),
          ),
        )
        .catch(() => setConnectedChannels([]));
    }
  }, [open]);

  const getVal = (slotName: string, fallback: string) => values[slotName] ?? fallback;
  const setVal = (slotName: string, val: string) =>
    setValues((prev) => ({ ...prev, [slotName]: val }));

  const handleSubmit = useCallback(async () => {
    if (!blueprint) return;
    setSaving(true);
    try {
      const merged = Object.fromEntries(
        blueprint.slots.map((s) => [s.name, values[s.name] ?? s.default]),
      );
      const delivery = deliveryChannel !== 'chat'
        ? { channel: toApiChannel(deliveryChannel), ...(deliveryTarget.trim() ? { target: deliveryTarget.trim() } : {}) }
        : undefined;
      const payload = buildJobPayload(blueprint, merged, userTz, t, delivery);
      await createJob(payload);
      toast.success(t('createSuccess'));
      setValues({});
      setDeliveryChannel('chat');
      setDeliveryTarget('');
      onOpenChange(false);
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  }, [blueprint, values, userTz, deliveryChannel, deliveryTarget, createJob, t, onOpenChange]);

  if (!blueprint) return null;

  const displayTitle = blueprint.title?.[locale] || t(blueprint.titleKey);
  const displayDesc = blueprint.description?.[locale] || t(blueprint.descKey);

  const previewSchedule = blueprint.buildSchedule(
    Object.fromEntries(blueprint.slots.map((s) => [s.name, values[s.name] ?? s.default])),
  );

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) { setValues({}); setDeliveryChannel('chat'); setDeliveryTarget(''); } onOpenChange(v); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <blueprint.icon className="h-5 w-5 text-primary" />
            {displayTitle}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-2">
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
                    {WEEKDAY_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {t(opt.labelKey)}
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

          {/* Delivery channel */}
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

          <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
            <p className="text-xs text-muted-foreground">
              <Sparkles className="h-3 w-3 inline mr-1" />
              {humanizeSchedule(previewSchedule)}
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" size="sm" onClick={() => { setValues({}); setDeliveryChannel('chat'); setDeliveryTarget(''); onOpenChange(false); }} disabled={saving}>
              {t('cancel')}
            </Button>
            <Button size="sm" onClick={handleSubmit} disabled={saving} className="gap-1.5">
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {t('createSubmit')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
