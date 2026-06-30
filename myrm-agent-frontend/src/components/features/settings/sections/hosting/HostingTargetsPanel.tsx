'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import {
  deleteHostingTarget,
  fetchHostingTargets,
  saveHostingTarget,
  saveTargetCredentials,
  testHostingTarget,
  PROVIDER_LABELS,
  type HostingProviderType,
  type HostingTarget,
} from '@/services/hosting';
import { toast } from 'sonner';
import { Loader2, Plus, Trash2 } from 'lucide-react';

const PROVIDERS: HostingProviderType[] = ['vercel', 'cloudflare_pages', 'netlify', 'http_webhook'];

const DEFAULT_NAMES: Record<HostingProviderType, string> = {
  vercel: 'Vercel',
  cloudflare_pages: 'Cloudflare Pages',
  netlify: 'Netlify',
  http_webhook: 'Custom Webhook',
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
        const ok = await saveTargetCredentials(
          target.id,
          Object.fromEntries(credKeys),
        );
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
      for (const item of targets) {
        await saveHostingTarget({
          id: item.id,
          name: item.name,
          provider_type: item.provider_type,
          config: item.config,
          is_default: item.id === target.id,
        });
      }
      await load();
      toast.success(t('defaultUpdated'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('loading')}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">{t('title')}</h2>
        <p className="text-sm text-muted-foreground mt-1">{t('description')}</p>
      </div>

      {targets.length === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center space-y-3">
          <p className="text-sm text-muted-foreground">{t('empty')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {targets.map((target) => {
            const draft = drafts[target.id] ?? {
              name: target.name,
              config: { ...target.config },
              credentials: {},
            };
            return (
              <div key={target.id} className="rounded-lg border p-4 space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-1 min-w-0">
                    <p className="font-medium truncate">{target.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {PROVIDER_LABELS[target.provider_type]}
                      {target.is_default ? ` · ${t('default')}` : ''}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2 shrink-0">
                    {!target.is_default && (
                      <Button variant="outline" size="sm" disabled={saving} onClick={() => void handleSetDefault(target)}>
                        {t('setDefault')}
                      </Button>
                    )}
                    <Button variant="ghost" size="icon" onClick={() => void handleDelete(target.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2 sm:col-span-2">
                    <Label htmlFor={`name-${target.id}`}>{t('targetName')}</Label>
                    <Input
                      id={`name-${target.id}`}
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
                  <Button variant="default" size="sm" disabled={saving} onClick={() => void handleSaveTarget(target)}>
                    {t('saveTarget')}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => void handleTest(target.id)}>
                    {t('testConnection')}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="rounded-lg border border-dashed p-4 space-y-3">
        <p className="text-sm font-medium">{t('addTarget')}</p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="space-y-2 flex-1">
            <Label htmlFor="add-provider">{t('providerType')}</Label>
            <select
              id="add-provider"
              value={addProvider}
              onChange={(e) => setAddProvider(e.target.value as HostingProviderType)}
              className="w-full h-10 rounded-md border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-950 px-3 text-sm"
            >
              {PROVIDERS.map((provider) => (
                <option key={provider} value={provider}>
                  {PROVIDER_LABELS[provider]}
                </option>
              ))}
            </select>
          </div>
          <Button onClick={() => void handleAddTarget()} disabled={saving}>
            <Plus className="h-4 w-4 mr-2" />
            {t('addTargetButton')}
          </Button>
        </div>
      </div>
    </div>
  );
}
