'use client';

import { memo, useState, useCallback, useEffect, useMemo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Switch } from '@/components/primitives/switch';
import { Skeleton } from '@/components/primitives/skeleton';
import { Webhook, Plus, Trash2, RefreshCw, Send, CheckCircle2, AlertCircle, Shield, Pencil } from 'lucide-react';
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
import WebhookEndpointForm, {
  AVAILABLE_WEBHOOK_EVENT_IDS,
  type WebhookEndpointFormValues,
} from './WebhookEndpointForm';

const DEFAULT_EVENTS = ['session_completed', 'session_failed', 'approval_required'];

const emptyFormValues = (): WebhookEndpointFormValues => ({
  name: '',
  url: '',
  secret: '',
  agentId: null,
  events: [...DEFAULT_EVENTS],
});

export const LifecycleWebhookSection = memo(() => {
  const t = useTranslations('settings.lifecycleWebhook');
  const locale = useLocale();
  const [webhooks, setWebhooks] = useState<LifecycleWebhook[]>([]);
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [createForm, setCreateForm] = useState<WebhookEndpointFormValues>(emptyFormValues);
  const [editForm, setEditForm] = useState<WebhookEndpointFormValues>(emptyFormValues);
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

  const closeCreateForm = () => {
    setShowAddForm(false);
    setCreateForm(emptyFormValues());
  };

  const closeEditForm = () => {
    setEditingId(null);
    setEditForm(emptyFormValues());
  };

  const openEditForm = (hook: LifecycleWebhook) => {
    setShowAddForm(false);
    setCreateForm(emptyFormValues());
    setEditingId(hook.id);
    setEditForm({
      name: hook.name,
      url: hook.url,
      secret: '',
      agentId: hook.agent_id ?? null,
      events: hook.events.length > 0 ? [...hook.events] : [...DEFAULT_EVENTS],
    });
  };

  const handleCreate = async () => {
    if (!createForm.name.trim() || !createForm.url.trim()) return;
    try {
      setSubmitting(true);
      await createLifecycleWebhook({
        name: createForm.name.trim(),
        url: createForm.url.trim(),
        secret: createForm.secret.trim() || undefined,
        events: createForm.events,
        agent_id: createForm.agentId,
        is_active: true,
      });
      closeCreateForm();
      await fetchWebhooks();
    } catch {
      // Handled by API error toast
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdate = async (hook: LifecycleWebhook) => {
    if (!editForm.name.trim() || !editForm.url.trim()) return;
    try {
      setSubmitting(true);
      const originalAgentId = hook.agent_id ?? null;
      const payload: Parameters<typeof updateLifecycleWebhook>[1] = {
        name: editForm.name.trim(),
        url: editForm.url.trim(),
        events: editForm.events,
      };
      if (editForm.secret.trim()) {
        payload.secret = editForm.secret.trim();
      }
      if (editForm.agentId !== originalAgentId) {
        if (editForm.agentId === null) {
          payload.clear_agent_scope = true;
        } else {
          payload.agent_id = editForm.agentId;
        }
      }
      await updateLifecycleWebhook(hook.id, payload);
      closeEditForm();
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
      if (editingId === id) {
        closeEditForm();
      }
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

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Webhook className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium text-foreground">{t('endpointsTitle')}</span>
          </div>
          <Button
            size="sm"
            onClick={() => {
              if (showAddForm) {
                closeCreateForm();
              } else {
                closeEditForm();
                setShowAddForm(true);
              }
            }}
            className="gap-1.5"
          >
            <Plus className="h-3.5 w-3.5" />
            {showAddForm ? t('cancel') : t('addEndpoint')}
          </Button>
        </div>

        {showAddForm ? (
          <div className="rounded-xl border border-border/60 bg-muted/20 p-4 animate-in fade-in-50">
            <WebhookEndpointForm
              mode="create"
              values={createForm}
              agentOptions={agentOptions}
              submitting={submitting}
              onChange={(patch) => setCreateForm((prev) => ({ ...prev, ...patch }))}
              onCancel={closeCreateForm}
              onSubmit={handleCreate}
            />
          </div>
        ) : null}

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
                        aria-label={t('toggleActiveAriaLabel')}
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
                          {t(`events.${ev}` as `events.${(typeof AVAILABLE_WEBHOOK_EVENT_IDS)[number]}`)}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5 text-xs h-8"
                      onClick={() => (editingId === hook.id ? closeEditForm() : openEditForm(hook))}
                    >
                      <Pencil className="h-3 w-3" />
                      {editingId === hook.id ? t('cancel') : t('editEndpoint')}
                    </Button>
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

                {editingId === hook.id ? (
                  <div className="mt-4 pt-4 border-t border-border/40">
                    <WebhookEndpointForm
                      mode="edit"
                      values={editForm}
                      hasExistingSecret={Boolean(hook.has_secret || hook.secret)}
                      agentOptions={agentOptions}
                      submitting={submitting}
                      onChange={(patch) => setEditForm((prev) => ({ ...prev, ...patch }))}
                      onCancel={closeEditForm}
                      onSubmit={() => handleUpdate(hook)}
                    />
                  </div>
                ) : null}

                {pingResult && pingResult.id === hook.id ? (
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
                ) : null}
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
