'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Zap, Plus, Trash2, Webhook, MessageSquare, Server, Copy, Eye, EyeOff, Terminal } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { EditorToggle } from './EditorToggle';
import { toast } from 'sonner';
import type { CronJob } from '@/services/cron';
import { updateCronJob } from '@/services/cron';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { useIngressUrl } from '@/hooks/useIngressUrl';

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

function isValidRegex(pattern: string): boolean {
  if (!pattern) return true;
  try {
    new RegExp(pattern);
    return true;
  } catch {
    return false;
  }
}

function buildCurlExample(url: string, secret?: string | null): string {
  const secretHeader = secret ? `\n  -H "x-webhook-secret: ${secret}" \\` : '';
  return `curl -X POST "${url}" \\${secretHeader}\n  -H "Content-Type: application/json" \\\n  -d '{"event": "test"}'`;
}

function WebhookDisplay({ path, secret }: { path?: string | null; secret?: string | null }) {
  const t = useTranslations('cron');
  const [showSecret, setShowSecret] = useState(false);
  const [showCurl, setShowCurl] = useState(false);

  const { url: webhookUrl, loading } = useIngressUrl(`/api/v1/cron/triggers/webhook/${path || ''}`);
  const isLocalhost = webhookUrl.includes('localhost') || webhookUrl.includes('127.0.0.1');

  const copyToClipboard = useCallback((text: string) => {
    writeToClipboard(text);
    toast.success('Copied');
  }, []);

  if (!path) return null;

  const curlCmd = buildCurlExample(webhookUrl, secret);

  return (
    <div className="rounded border bg-muted/30 px-2 py-1.5 space-y-1">
      <div className="flex items-center gap-1.5 text-xs">
        <span className="text-muted-foreground shrink-0">{t('triggerWebhookUrl')}:</span>
        {loading ? (
          <div className="h-4 flex-1 bg-muted/50 rounded animate-pulse" />
        ) : (
          <code className="text-[10px] font-mono truncate flex-1">{webhookUrl}</code>
        )}
        <button
          onClick={() => copyToClipboard(webhookUrl)}
          disabled={loading}
          className="shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-50"
        >
          <Copy className="h-3 w-3" />
        </button>
      </div>
      {!loading && isLocalhost && (
        <div className="text-[10px] text-amber-500 italic mt-0.5 leading-relaxed">
          {t('triggerLocalhostWarning')}{' '}
          <Link href="/settings/system#public-access" className="underline font-medium not-italic hover:text-amber-400">
            {t('triggerOpenSystemSettings')}
          </Link>
        </div>
      )}
      {secret && (
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground shrink-0">{t('triggerWebhookSecret')}:</span>
          <code className="text-[10px] font-mono truncate flex-1">{showSecret ? secret : '••••••••••••'}</code>
          <button
            onClick={() => setShowSecret(!showSecret)}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            {showSecret ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
          </button>
          <button
            onClick={() => copyToClipboard(secret)}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            <Copy className="h-3 w-3" />
          </button>
        </div>
      )}
      <div className="flex items-center gap-1.5 text-xs">
        <button
          onClick={() => setShowCurl(!showCurl)}
          className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
        >
          <Terminal className="h-3 w-3" />
          <span className="text-[10px]">{t('triggerWebhookCurl')}</span>
        </button>
      </div>
      {showCurl && (
        <div className="relative rounded bg-background/80 p-1.5">
          <pre className="text-[10px] font-mono whitespace-pre-wrap break-all text-foreground/80">{curlCmd}</pre>
          <button
            onClick={() => copyToClipboard(curlCmd)}
            className="absolute top-1 right-1 text-muted-foreground hover:text-foreground"
          >
            <Copy className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}

export function TriggerEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const tc = job.triggers;
  const hasAny = !!(tc && (tc.webhooks.length > 0 || tc.events.length > 0 || tc.system_events.length > 0));

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

  useEffect(() => {
    const newTc = job.triggers;
    const newHas = !!(
      newTc &&
      (newTc.webhooks.length > 0 || newTc.events.length > 0 || newTc.system_events.length > 0)
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
    const hasInvalidRegex = eventDrafts.some((e) => e.pattern.trim() && !isValidRegex(e.pattern));
    if (hasInvalidRegex) {
      toast.error(t('triggerEventPatternInvalid'));
      return;
    }
    setSaving(true);
    try {
      const triggers: {
        webhooks: Record<string, never>[];
        events: { pattern: string; channel?: string }[];
        system_events: { source: string; event_type: string; filters?: Record<string, string> }[];
      } = {
        webhooks: Array.from({ length: webhookCount }, () => ({})),
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
      };
      await updateCronJob(job.id, { triggers });
      onUpdated();
      toast.success(t('triggersUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  }, [job.id, webhookCount, eventDrafts, systemDrafts, onUpdated, t]);

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
              <WebhookDisplay key={i} path={wh.path} secret={wh.secret} />
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
              const valid = isValidRegex(draft.pattern);
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
