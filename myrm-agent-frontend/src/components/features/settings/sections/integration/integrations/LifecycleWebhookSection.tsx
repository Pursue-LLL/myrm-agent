'use client';

import { memo, useState, useCallback, useEffect, useMemo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { Skeleton } from '@/components/primitives/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Webhook, Plus, Trash2, RefreshCw, Send, CheckCircle2, AlertCircle, Shield, Key } from 'lucide-react';
import SettingsSection from '../../SettingsSection';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { listAgents, type AgentListItem } from '@/services/agent';
import {
  listLifecycleWebhooks,
  createLifecycleWebhook,
  updateLifecycleWebhook,
  deleteLifecycleWebhook,
  pingSavedLifecycleWebhook,
  type LifecycleWebhook,
  type WebhookPingResult,
} from '@/services/lifecycleWebhook';

const AVAILABLE_EVENT_IDS = [
  'session_completed',
  'session_failed',
  'approval_required',
  'approval_resolved',
  'kanban_task_updated',
  'goal_terminal',
  'subagent_spawned',
  'subagent_merged',
] as const;

export const LifecycleWebhookSection = memo(() => {
  const t = useTranslations('settings.lifecycleWebhook');
  const locale = useLocale();
  const [webhooks, setWebhooks] = useState<LifecycleWebhook[]>([]);
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);

  // Add/Edit form state
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [secret, setSecret] = useState('');
  const [agentId, setAgentId] = useState<string | null>(null);
  const [selectedEvents, setSelectedEvents] = useState<string[]>([
    'session_completed',
    'session_failed',
    'approval_required',
  ]);
  const [submitting, setSubmitting] = useState(false);
  const [pingLoading, setPingLoading] = useState<string | null>(null);
  const [pingResult, setPingResult] = useState<{ id: string; result: WebhookPingResult } | null>(null);

  const agentLabelById = useMemo(() => {
    const labels = new Map<string, string>();
    for (const agent of agents) {
      labels.set(agent.id, getBuiltinAgentName(agent.id, agent.name, locale));
    }
    return labels;
  }, [agents, locale]);

  const agentOptions = useMemo(() => {
    return agents.map((agent) => ({
      id: agent.id,
      label: agentLabelById.get(agent.id) ?? agent.name,
    }));
  }, [agents, agentLabelById]);

  const fetchWebhooks = useCallback(async () => {
    try {
      setLoading(true);
      const [webhookData, agentResponse] = await Promise.all([listLifecycleWebhooks(), listAgents(1, 100)]);
      setWebhooks(Array.isArray(webhookData) ? webhookData : []);
      setAgents(agentResponse.items);
    } catch {
      setWebhooks([]);
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWebhooks();
  }, [fetchWebhooks]);

  const handleCreate = async () => {
    if (!name.trim() || !url.trim()) return;
    try {
      setSubmitting(true);
      await createLifecycleWebhook({
        name: name.trim(),
        url: url.trim(),
        secret: secret.trim() || undefined,
        events: selectedEvents,
        agent_id: agentId,
        is_active: true,
      });
      setName('');
      setUrl('');
      setSecret('');
      setAgentId(null);
      setShowAddForm(false);
      await fetchWebhooks();
    } catch {
      // Handled by API error toast
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggle = async (webhook: LifecycleWebhook) => {
    try {
      await updateLifecycleWebhook(webhook.id, { is_active: !webhook.is_active });
      setWebhooks((prev) =>
        prev.map((item) => (item.id === webhook.id ? { ...item, is_active: !item.is_active } : item)),
      );
    } catch {
      // Error handled
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteLifecycleWebhook(id);
      setWebhooks((prev) => prev.filter((item) => item.id !== id));
    } catch {
      // Error handled
    }
  };

  const handlePing = async (webhook: LifecycleWebhook) => {
    try {
      setPingLoading(webhook.id);
      const res = await pingSavedLifecycleWebhook(webhook.id);
      setPingResult({ id: webhook.id, result: res });
    } catch {
      setPingResult({
        id: webhook.id,
        result: { success: false, latency_ms: 0, error: t('pingConnectionError') },
      });
    } finally {
      setPingLoading(null);
    }
  };

  const generateSecret = () => {
    const randomBytes = new Uint8Array(16);
    crypto.getRandomValues(randomBytes);
    const hex = Array.from(randomBytes)
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
    setSecret(`whsec_${hex}`);
  };

  const toggleEventSelection = (eventId: string) => {
    setSelectedEvents((prev) => (prev.includes(eventId) ? prev.filter((id) => id !== eventId) : [...prev, eventId]));
  };

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Webhook className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium text-foreground">{t('endpointsTitle')}</span>
          </div>
          <Button size="sm" onClick={() => setShowAddForm((v) => !v)} className="gap-1.5">
            <Plus className="h-3.5 w-3.5" />
            {showAddForm ? t('cancel') : t('addEndpoint')}
          </Button>
        </div>

        {/* Add Form Drawer */}
        {showAddForm && (
          <div className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-4 animate-in fade-in-50">
            <h4 className="text-sm font-semibold text-foreground">{t('newEndpoint')}</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t('endpointName')}</label>
                <Input
                  placeholder="e.g. Feishu Alert Bot, CI Pipeline"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t('payloadUrl')}</label>
                <Input
                  placeholder="https://example.com/api/webhook"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t('agentScope')}</label>
              <Select value={agentId ?? 'all'} onValueChange={(value) => setAgentId(value === 'all' ? null : value)}>
                <SelectTrigger className="w-full sm:max-w-md">
                  <SelectValue placeholder={t('agentScopeAll')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('agentScopeAll')}</SelectItem>
                  {agentOptions.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">{t('agentScopeHint')}</p>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                  <Key className="h-3.5 w-3.5" />
                  {t('signingSecret')}
                </label>
                <button
                  type="button"
                  onClick={generateSecret}
                  className="text-[11px] text-primary hover:underline cursor-pointer"
                >
                  {t('generateRandom')}
                </button>
              </div>
              <Input
                placeholder={t('signingSecretPlaceholder')}
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">{t('subscribedEvents')}</label>
              <div className="flex flex-wrap gap-1.5">
                {AVAILABLE_EVENT_IDS.map((ev) => {
                  const active = selectedEvents.includes(ev);
                  return (
                    <Badge
                      key={ev}
                      variant={active ? 'default' : 'outline'}
                      className="cursor-pointer transition text-[11px] py-1 px-2.5"
                      onClick={() => toggleEventSelection(ev)}
                    >
                      {t(`events.${ev}`)}
                    </Badge>
                  );
                })}
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-border/40">
              <Button variant="ghost" size="sm" onClick={() => setShowAddForm(false)}>
                {t('cancel')}
              </Button>
              <Button size="sm" onClick={handleCreate} disabled={!name.trim() || !url.trim() || submitting}>
                {submitting ? t('saving') : t('saveEndpoint')}
              </Button>
            </div>
          </div>
        )}

        {/* Endpoints List */}
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full rounded-xl" />
            <Skeleton className="h-20 w-full rounded-xl" />
          </div>
        ) : webhooks.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/60 p-8 text-center">
            <Webhook className="mx-auto h-8 w-8 text-muted-foreground/40 mb-2" />
            <p className="text-sm font-medium text-foreground mb-1">{t('noEndpoints')}</p>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">{t('noEndpointsDesc')}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {webhooks.map((hook) => (
              <div
                key={hook.id}
                className={cn(
                  'rounded-xl border p-4 transition-all bg-card/40 border-border/50 hover:border-border/80',
                  !hook.is_active && 'opacity-60 bg-muted/10',
                )}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-foreground">{hook.name}</span>
                      <Switch
                        checked={hook.is_active}
                        onCheckedChange={() => handleToggle(hook)}
                        aria-label="Toggle Webhook"
                      />
                      {hook.has_secret || hook.secret ? (
                        <Badge variant="secondary" className="text-[10px] gap-1 px-1.5 py-0">
                          <Shield className="h-2.5 w-2.5 text-emerald-500" />
                          HMAC
                        </Badge>
                      ) : null}
                      {hook.agent_id ? (
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                          {agentLabelById.get(hook.agent_id) ?? hook.agent_id}
                        </Badge>
                      ) : null}
                      {hook.last_delivery_status ? (
                        <Badge
                          variant={hook.last_delivery_status < 300 ? 'default' : 'destructive'}
                          className="text-[10px] px-1.5 py-0"
                        >
                          HTTP {hook.last_delivery_status}
                        </Badge>
                      ) : null}
                    </div>
                    <p className="text-xs font-mono text-muted-foreground truncate max-w-lg">{hook.url}</p>
                    <div className="flex items-center gap-1.5 flex-wrap pt-1">
                      {hook.events.map((ev) => (
                        <span key={ev} className="text-[10px] bg-muted/60 text-muted-foreground px-1.5 py-0.5 rounded">
                          {t(`events.${ev}` as `events.${typeof AVAILABLE_EVENT_IDS[number]}`)}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5 text-xs h-8"
                      onClick={() => handlePing(hook)}
                      disabled={pingLoading === hook.id}
                    >
                      {pingLoading === hook.id ? (
                        <RefreshCw className="h-3 w-3 animate-spin" />
                      ) : (
                        <Send className="h-3 w-3" />
                      )}
                      {t('testPing')}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                      onClick={() => handleDelete(hook.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                {/* Ping probe status feedback */}
                {pingResult && pingResult.id === hook.id && (
                  <div
                    className={cn(
                      'mt-3 rounded-lg border p-2.5 text-xs flex items-center justify-between',
                      pingResult.result.success
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                        : 'border-destructive/30 bg-destructive/10 text-destructive',
                    )}
                  >
                    <div className="flex items-center gap-2">
                      {pingResult.result.success ? (
                        <CheckCircle2 className="h-4 w-4" />
                      ) : (
                        <AlertCircle className="h-4 w-4" />
                      )}
                      <span>
                        {pingResult.result.success
                          ? t('pingSuccess', {
                              status: pingResult.result.status_code ?? 0,
                              latency: Math.round(pingResult.result.latency_ms),
                            })
                          : t('pingFailed', {
                              error: pingResult.result.error || t('pingConnectionError'),
                            })}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setPingResult(null)}
                      className="text-xs opacity-70 hover:opacity-100"
                    >
                      ×
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </SettingsSection>
  );
});

LifecycleWebhookSection.displayName = 'LifecycleWebhookSection';
export default LifecycleWebhookSection;
