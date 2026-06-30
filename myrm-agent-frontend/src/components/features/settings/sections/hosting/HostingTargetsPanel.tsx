'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import {
  deleteHostingTarget,
  fetchHostingTargets,
  makeDefaultHostingTarget,
  saveHostingTarget,
  saveTargetCredentials,
  testHostingTarget,
  PROVIDER_LABELS,
  type HostingProviderType,
  type HostingTarget,
} from '@/services/hosting';
import { toast } from 'sonner';
import { Cloud, Globe, Loader2, Plus, Radio, Trash2, Webhook, Zap } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

const PROVIDERS: HostingProviderType[] = ['vercel', 'cloudflare_pages', 'netlify', 'http_webhook'];

const DEFAULT_NAMES: Record<HostingProviderType, string> = {
  vercel: 'Vercel',
  cloudflare_pages: 'Cloudflare Pages',
  netlify: 'Netlify',
  http_webhook: 'Custom Webhook',
};

const PROVIDER_ICONS: Record<HostingProviderType, React.ComponentType<{ className?: string }>> = {
  vercel: Zap,
  cloudflare_pages: Cloud,
  netlify: Globe,
  http_webhook: Webhook,
};

interface TargetDraft {
  name: string;
  config: Record<string, string>;
  credentials: Record<string, string>;
}

function emptyDraft(provider: HostingProviderType): TargetDraft {
  return {
    name: DEFAULT_NAMES[provider],
    config: provider === 'http_webhook' ? { allow_http: 'false' } : {},
    credentials: {},
  };
}

function configFields(provider: HostingProviderType): Array<{ key: string; labelKey: string; secret?: boolean }> {
  switch (provider) {
    case 'cloudflare_pages':
      return [
        { key: 'account_id', labelKey: 'cloudflareAccountId' },
        { key: 'project_name', labelKey: 'cloudflareProjectName' },
      ];
    case 'netlify':
      return [{ key: 'site_id', labelKey: 'netlifySiteId' }];
    case 'http_webhook':
      return [
        { key: 'webhook_url', labelKey: 'webhookUrl' },
        { key: 'allow_http', labelKey: 'allowHttp' },
      ];
    default:
      return [];
  }
}

function credentialFields(provider: HostingProviderType): Array<{ key: string; labelKey: string }> {
  switch (provider) {
    case 'vercel':
      return [{ key: 'token', labelKey: 'vercelToken' }];
    case 'cloudflare_pages':
      return [{ key: 'api_token', labelKey: 'cloudflareToken' }];
    case 'netlify':
      return [{ key: 'access_token', labelKey: 'netlifyToken' }];
    case 'http_webhook':
      return [
        { key: 'auth_header', labelKey: 'webhookAuthHeader' },
        { key: 'auth_value', labelKey: 'webhookAuthValue' },
      ];
    default:
      return [];
  }
}

export default function HostingTargetsPanel() {
  const t = useTranslations('settings.hosting');
  const [targets, setTargets] = useState<HostingTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, TargetDraft>>({});
  const [addProvider, setAddProvider] = useState<HostingProviderType>('vercel');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTargets(await fetchHostingTargets());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const updateDraft = (targetId: string, patch: Partial<TargetDraft>) => {
    setDrafts((prev) => ({
      ...prev,
      [targetId]: {
        ...(prev[targetId] ?? { name: '', config: {}, credentials: {} }),
        ...patch,
        config: { ...(prev[targetId]?.config ?? {}), ...(patch.config ?? {}) },
        credentials: { ...(prev[targetId]?.credentials ?? {}), ...(patch.credentials ?? {}) },
      },
    }));
  };

  const handleAddTarget = async () => {
    setSaving(true);
    try {
      const draft = emptyDraft(addProvider);
      const created = await saveHostingTarget({
        name: draft.name,
        provider_type: addProvider,
        config: draft.config,
        is_default: targets.length === 0,
      });
      if (!created) {
        toast.error(t('saveFailed'));
        return;
      }
      await load();
      toast.success(t('added'));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveTarget = async (target: HostingTarget) => {
    const draft = drafts[target.id];
    if (!draft) {
      return;
    }
    setSaving(true);
    try {
      const saved = await saveHostingTarget({
        id: target.id,
        name: draft.name || target.name,
        provider_type: target.provider_type,
        config: { ...target.config, ...draft.config },
        is_default: target.is_default,
      });
      if (!saved) {
        toast.error(t('saveFailed'));
        return;
      }
      const credKeys = Object.entries(draft.credentials).filter(([, value]) => value.trim());
      if (credKeys.length > 0) {
        const ok = await saveTargetCredentials(target.id, Object.fromEntries(credKeys));
        if (!ok) {
          toast.error(t('saveFailed'));
          return;
        }
      }
      toast.success(t('saved'));
      await load();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (targetId: string) => {
    const ok = await deleteHostingTarget(targetId);
    if (ok) {
      await load();
      toast.success(t('deleted'));
    } else {
      toast.error(t('deleteFailed'));
    }
  };

  const handleTest = async (targetId: string) => {
    const result = await testHostingTarget(targetId);
    if (result.ok) {
      toast.success(result.message);
    } else {
      toast.error(result.message);
    }
  };

  const handleSetDefault = async (target: HostingTarget) => {
    setSaving(true);
    try {
      const updated = await makeDefaultHostingTarget(target.id);
      if (!updated) {
        toast.error(t('defaultUpdateFailed'));
        return;
      }
      await load();
      toast.success(t('defaultUpdated'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        {t('loading')}
      </div>
    );
  }

  return (
    <div className="flex flex-col space-y-6 p-4 sm:p-6 lg:p-8 bg-secondary/30 dark:bg-secondary/20 rounded-2xl border border-border/50">
      <div className="space-y-2">
        <h2 className="text-lg font-semibold text-foreground">{t('title')}</h2>
        <p className="text-sm text-muted-foreground leading-relaxed">{t('description')}</p>
      </div>

      <div className="rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/10 via-background to-background p-4 sm:p-5 space-y-4">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <Radio className="h-4 w-4 text-primary" />
          {t('workflowTitle')}
        </div>
        <ol className="grid gap-3 sm:grid-cols-3 text-sm text-muted-foreground">
          {[t('workflowStep1'), t('workflowStep2'), t('workflowStep3')].map((step, index) => (
            <li
              key={step}
              className="flex gap-3 rounded-xl border border-border/60 bg-background/70 px-3 py-3"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
                {index + 1}
              </span>
              <span className="leading-snug">{step}</span>
            </li>
          ))}
        </ol>
        <p className="text-xs text-muted-foreground">{t('zeroTokenHint')}</p>
      </div>

      {targets.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border/80 bg-background/50 p-6 sm:p-8 text-center space-y-3">
          <Globe className="mx-auto h-8 w-8 text-primary/70" />
          <p className="text-sm text-muted-foreground max-w-md mx-auto">{t('empty')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {targets.map((target) => {
            const draft = drafts[target.id] ?? {
              name: target.name,
              config: { ...target.config },
              credentials: {},
            };
            const ProviderIcon = PROVIDER_ICONS[target.provider_type];
            return (
              <div
                key={target.id}
                className="rounded-2xl border border-border/70 bg-background/80 p-4 sm:p-5 space-y-4"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex gap-3 min-w-0">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <ProviderIcon className="h-5 w-5" />
                    </div>
                    <div className="space-y-1 min-w-0">
                      <p className="font-medium truncate text-foreground">{target.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {PROVIDER_LABELS[target.provider_type]}
                        {target.is_default ? ` · ${t('default')}` : ''}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 shrink-0">
                    {!target.is_default && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="rounded-xl"
                        disabled={saving}
                        onClick={() => void handleSetDefault(target)}
                      >
                        {t('setDefault')}
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="rounded-xl"
                      onClick={() => void handleDelete(target.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2 sm:col-span-2">
                    <Label htmlFor={`name-${target.id}`}>{t('targetName')}</Label>
                    <Input
                      id={`name-${target.id}`}
                      className="rounded-xl bg-background"
                      value={draft.name}
                      onChange={(e) => updateDraft(target.id, { name: e.target.value })}
                    />
                  </div>

                  {configFields(target.provider_type).map((field) => (
                    <div key={field.key} className="space-y-2">
                      <Label htmlFor={`${target.id}-${field.key}`}>{t(field.labelKey)}</Label>
                      <Input
                        id={`${target.id}-${field.key}`}
                        type={field.secret ? 'password' : 'text'}
                        className="rounded-xl bg-background"
                        value={draft.config[field.key] ?? target.config[field.key] ?? ''}
                        onChange={(e) =>
                          updateDraft(target.id, {
                            config: { [field.key]: e.target.value },
                          })
                        }
                        placeholder={t(`${field.labelKey}Placeholder`)}
                      />
                    </div>
                  ))}

                  {credentialFields(target.provider_type).map((field) => (
                    <div key={field.key} className="space-y-2">
                      <Label htmlFor={`${target.id}-cred-${field.key}`}>{t(field.labelKey)}</Label>
                      <Input
                        id={`${target.id}-cred-${field.key}`}
                        type="password"
                        className="rounded-xl bg-background font-mono text-sm"
                        value={draft.credentials[field.key] ?? ''}
                        onChange={(e) =>
                          updateDraft(target.id, {
                            credentials: { [field.key]: e.target.value },
                          })
                        }
                        placeholder={t(`${field.labelKey}Placeholder`)}
                      />
                    </div>
                  ))}
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="default"
                    size="sm"
                    className="rounded-xl"
                    disabled={saving}
                    onClick={() => void handleSaveTarget(target)}
                  >
                    {t('saveTarget')}
                  </Button>
                  <Button variant="outline" size="sm" className="rounded-xl" onClick={() => void handleTest(target.id)}>
                    {t('testConnection')}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="rounded-2xl border border-dashed border-border/80 bg-background/40 p-4 sm:p-5 space-y-4">
        <p className="text-sm font-medium text-foreground">{t('addTarget')}</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          {PROVIDERS.map((provider) => {
            const Icon = PROVIDER_ICONS[provider];
            const selected = addProvider === provider;
            return (
              <button
                key={provider}
                type="button"
                onClick={() => setAddProvider(provider)}
                className={cn(
                  'flex flex-col items-start gap-2 rounded-xl border px-3 py-3 text-left transition-colors',
                  selected
                    ? 'border-primary bg-primary/10 text-foreground'
                    : 'border-border/70 bg-background/60 text-muted-foreground hover:border-primary/40 hover:bg-background',
                )}
              >
                <Icon className={cn('h-4 w-4', selected ? 'text-primary' : 'text-muted-foreground')} />
                <span className="text-xs font-medium leading-tight">{PROVIDER_LABELS[provider]}</span>
              </button>
            );
          })}
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground max-w-lg">{t(`providerHint.${addProvider}`)}</p>
          <Button onClick={() => void handleAddTarget()} disabled={saving} className="rounded-xl shrink-0">
            <Plus className="h-4 w-4 mr-2" />
            {t('addTargetButton')}
          </Button>
        </div>
      </div>
    </div>
  );
}
