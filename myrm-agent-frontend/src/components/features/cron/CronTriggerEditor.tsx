'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Zap, Plus, Trash2, Webhook, MessageSquare, Server, Terminal } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { EditorToggle } from './EditorToggle';
import { toast } from 'sonner';
import type { CronJob } from '@/services/cron';
import { updateCronJob } from '@/services/cron';
import { CronTriggerWebhookDisplay, isValidCronTriggerRegex } from './CronTriggerWebhookDisplay';
import { StreamTriggerSection, type StreamDraft } from './StreamTriggerSection';
import { PollTriggerSection, type PollDraft } from './PollTriggerSection';

interface EditorProps {
  job: CronJob;
  onUpdated: () => void;
}

interface EventDraft {
  pattern: string;
  channel: string;
}

interface SystemEventDraft {
  source: string;
  event_type: string;
  filters: string;
}

export function TriggerEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const tc = job.triggers;
  const hasAny = !!(
    tc &&
    (tc.webhooks.length > 0 ||
      tc.events.length > 0 ||
      tc.system_events.length > 0 ||
      (tc.streams?.length ?? 0) > 0 ||
      (tc.polls?.length ?? 0) > 0)
  );

  const [enabled, setEnabled] = useState(hasAny);
  const [saving, setSaving] = useState(false);

  const [eventDrafts, setEventDrafts] = useState<EventDraft[]>(
    tc?.events.map((e) => ({ pattern: e.pattern, channel: e.channel ?? '' })) ?? [],
  );
  const [systemDrafts, setSystemDrafts] = useState<SystemEventDraft[]>(
    tc?.system_events.map((s) => ({
      source: s.source,
      event_type: s.event_type,
      filters: Object.entries(s.filters)
        .map(([k, v]) => `${k}=${v}`)
        .join(', '),
    })) ?? [],
  );
  const [webhookCount, setWebhookCount] = useState(tc?.webhooks.length ?? 0);
  const [streamDrafts, setStreamDrafts] = useState<StreamDraft[]>(
    tc?.streams?.map((s) => ({
      url: s.url,
      protocol: s.protocol,
      filter_json_path: s.filter_json_path ?? '',
      filter_regex: s.filter_regex ?? '',
    })) ?? [],
  );
  const [pollDrafts, setPollDrafts] = useState<PollDraft[]>(
    tc?.polls?.map((p) => ({
      url: p.url,
      json_path: p.json_path ?? '',
      interval_seconds: p.interval_seconds,
    })) ?? [],
  );

  useEffect(() => {
    const newTc = job.triggers;
    const newHas = !!(
      newTc &&
      (newTc.webhooks.length > 0 ||
        newTc.events.length > 0 ||
        newTc.system_events.length > 0 ||
        (newTc.streams?.length ?? 0) > 0 ||
        (newTc.polls?.length ?? 0) > 0)
    );
    setEnabled(newHas);
    setEventDrafts(newTc?.events.map((e) => ({ pattern: e.pattern, channel: e.channel ?? '' })) ?? []);
    setSystemDrafts(
      newTc?.system_events.map((s) => ({
        source: s.source,
        event_type: s.event_type,
        filters: Object.entries(s.filters)
          .map(([k, v]) => `${k}=${v}`)
          .join(', '),
      })) ?? [],
    );
    setWebhookCount(newTc?.webhooks.length ?? 0);
    setStreamDrafts(
      newTc?.streams?.map((s) => ({
        url: s.url,
        protocol: s.protocol,
        filter_json_path: s.filter_json_path ?? '',
        filter_regex: s.filter_regex ?? '',
      })) ?? [],
    );
    setPollDrafts(
      newTc?.polls?.map((p) => ({
        url: p.url,
        json_path: p.json_path ?? '',
        interval_seconds: p.interval_seconds,
      })) ?? [],
    );
  }, [job.triggers]);

  const handleToggle = useCallback(
    async (on: boolean) => {
      if (!on) {
        setSaving(true);
        try {
          await updateCronJob(job.id, { triggers: null });
          onUpdated();
          toast.success(t('triggersCleared'));
        } catch {
          toast.error(t('actionFail'));
        } finally {
          setSaving(false);
        }
      }
      setEnabled(on);
    },
    [job.id, onUpdated, t],
  );

  const handleSave = useCallback(async () => {
    const hasInvalidRegex = eventDrafts.some((e) => e.pattern.trim() && !isValidCronTriggerRegex(e.pattern));
    if (hasInvalidRegex) {
      toast.error(t('triggerEventPatternInvalid'));
      return;
    }
    setSaving(true);
    try {
      const triggers = {
        webhooks: Array.from({ length: webhookCount }, () => ({})) as Record<string, never>[],
        events: eventDrafts
          .filter((e) => e.pattern.trim())
          .map((e) => ({ pattern: e.pattern.trim(), ...(e.channel ? { channel: e.channel } : {}) })),
        system_events: systemDrafts
          .filter((s) => s.source.trim() && s.event_type.trim())
          .map((s) => {
            const filters: Record<string, string> = {};
            s.filters.split(',').forEach((pair) => {
              const [k, v] = pair.split('=').map((x) => x.trim());
              if (k && v) filters[k] = v;
            });
            return { source: s.source.trim(), event_type: s.event_type.trim(), filters };
          }),
        streams: streamDrafts
          .filter((s) => s.url.trim())
          .map((s) => ({
            url: s.url.trim(),
            protocol: s.protocol,
            ...(s.filter_json_path ? { filter_json_path: s.filter_json_path.trim() } : {}),
            ...(s.filter_regex ? { filter_regex: s.filter_regex.trim() } : {}),
          })),
        polls: pollDrafts
          .filter((p) => p.url.trim())
          .map((p) => ({
            url: p.url.trim(),
            ...(p.json_path ? { json_path: p.json_path.trim() } : {}),
            interval_seconds: p.interval_seconds || 300,
          })),
      };
      await updateCronJob(job.id, { triggers });
      onUpdated();
      toast.success(t('triggersUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  }, [job.id, webhookCount, eventDrafts, systemDrafts, streamDrafts, pollDrafts, onUpdated, t]);

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Zap className="h-3.5 w-3.5" />
          <span>{t('triggersLabel')}</span>
        </div>
        <EditorToggle enabled={enabled} onToggle={() => void handleToggle(!enabled)} disabled={saving} />
      </div>
      <p className="text-[11px] text-muted-foreground">{t('triggersDesc')}</p>

      {enabled && (
        <div className="space-y-3 mt-1">
          {/* Webhooks */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Webhook className="h-3 w-3" />
              {t('triggerWebhookLabel')}
            </div>
            {tc?.webhooks.map((wh, i) => (
              <CronTriggerWebhookDisplay key={i} path={wh.path} secret={wh.secret} />
            ))}
            {webhookCount > (tc?.webhooks.length ?? 0) &&
              Array.from({ length: webhookCount - (tc?.webhooks.length ?? 0) }).map((_, i) => (
                <div key={`new-${i}`} className="text-[10px] text-muted-foreground italic">
                  {t('triggerWebhookDesc')}
                </div>
              ))}
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-[10px] gap-1"
              onClick={() => setWebhookCount((c) => c + 1)}
            >
              <Plus className="h-3 w-3" /> {t('triggerWebhookAdd')}
            </Button>
          </div>

          {/* Event Triggers */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <MessageSquare className="h-3 w-3" />
              {t('triggerEventLabel')}
            </div>
            {eventDrafts.map((draft, i) => {
              const valid = isValidCronTriggerRegex(draft.pattern);
              return (
                <div key={i} className="space-y-0.5">
                  <div className="flex items-center gap-1.5">
                    <Input
                      value={draft.pattern}
                      onChange={(e) => {
                        const next = [...eventDrafts];
                        next[i] = { ...next[i], pattern: e.target.value };
                        setEventDrafts(next);
                      }}
                      placeholder={t('triggerEventPattern')}
                      className={`h-7 text-xs font-mono flex-1 ${
                        draft.pattern && !valid
                          ? 'border-destructive focus-visible:ring-destructive/30'
                          : draft.pattern && valid
                            ? 'border-green-500/50 focus-visible:ring-green-500/30'
                            : ''
                      }`}
                    />
                    <Input
                      value={draft.channel}
                      onChange={(e) => {
                        const next = [...eventDrafts];
                        next[i] = { ...next[i], channel: e.target.value };
                        setEventDrafts(next);
                      }}
                      placeholder={t('triggerEventChannel')}
                      className="h-7 text-xs w-24"
                    />
                    <button
                      onClick={() => setEventDrafts(eventDrafts.filter((_, j) => j !== i))}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                  {draft.pattern && !valid && (
                    <p className="text-[10px] text-destructive pl-0.5">{t('triggerEventPatternInvalid')}</p>
                  )}
                </div>
              );
            })}
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-[10px] gap-1"
              onClick={() => setEventDrafts([...eventDrafts, { pattern: '', channel: '' }])}
            >
              <Plus className="h-3 w-3" /> {t('triggerEventAdd')}
            </Button>
          </div>

          {/* System Event Triggers */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Server className="h-3 w-3" />
              {t('triggerSystemEventLabel')}
            </div>
            {/* Quick presets */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {[
                { label: '@startup', source: 'app', event_type: 'startup' },
                { label: '@login', source: 'app', event_type: 'login' },
              ].map((preset) => {
                const exists = systemDrafts.some(
                  (d) => d.source === preset.source && d.event_type === preset.event_type,
                );
                return (
                  <Button
                    key={preset.label}
                    variant={exists ? 'secondary' : 'outline'}
                    size="sm"
                    className="h-5 text-[10px] gap-0.5 px-1.5"
                    disabled={exists}
                    onClick={() =>
                      setSystemDrafts([
                        ...systemDrafts,
                        { source: preset.source, event_type: preset.event_type, filters: '' },
                      ])
                    }
                  >
                    <Terminal className="h-2.5 w-2.5" />
                    {preset.label}
                  </Button>
                );
              })}
            </div>
            {systemDrafts.map((draft, i) => (
              <div key={i} className="flex items-center gap-1.5 flex-wrap">
                <Input
                  value={draft.source}
                  onChange={(e) => {
                    const next = [...systemDrafts];
                    next[i] = { ...next[i], source: e.target.value };
                    setSystemDrafts(next);
                  }}
                  placeholder={t('triggerSystemEventSource')}
                  className="h-7 text-xs w-24"
                />
                <Input
                  value={draft.event_type}
                  onChange={(e) => {
                    const next = [...systemDrafts];
                    next[i] = { ...next[i], event_type: e.target.value };
                    setSystemDrafts(next);
                  }}
                  placeholder={t('triggerSystemEventType')}
                  className="h-7 text-xs w-28"
                />
                <Input
                  value={draft.filters}
                  onChange={(e) => {
                    const next = [...systemDrafts];
                    next[i] = { ...next[i], filters: e.target.value };
                    setSystemDrafts(next);
                  }}
                  placeholder={t('triggerSystemEventFilters')}
                  className="h-7 text-xs flex-1"
                />
                <button
                  onClick={() => setSystemDrafts(systemDrafts.filter((_, j) => j !== i))}
                  className="text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-[10px] gap-1"
              onClick={() => setSystemDrafts([...systemDrafts, { source: '', event_type: '', filters: '' }])}
            >
              <Plus className="h-3 w-3" /> {t('triggerSystemEventAdd')}
            </Button>
          </div>

          {/* Stream Triggers */}
          <StreamTriggerSection drafts={streamDrafts} onChange={setStreamDrafts} />

          {/* Poll Triggers */}
          <PollTriggerSection drafts={pollDrafts} onChange={setPollDrafts} />

          {/* Save / Clear */}
          <div className="flex items-center gap-2 pt-1">
            <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
              {t('triggerSave')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
