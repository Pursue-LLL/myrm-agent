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
  type HostingProviderType,
  type HostingTarget,
} from '@/services/hosting';
import { toast } from 'sonner';
import { Loader2, Plus, Trash2 } from 'lucide-react';

const PROVIDERS: HostingProviderType[] = ['vercel', 'cloudflare_pages', 'netlify', 'http_webhook'];

export default function HostingTargetsPanel() {
  const t = useTranslations('settings.hosting');
  const [targets, setTargets] = useState<HostingTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

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

  const handleAddVercel = async () => {
    setSaving(true);
    try {
      const created = await saveHostingTarget({
        name: 'Vercel',
        provider_type: 'vercel',
        config: {},
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

  const handleSaveToken = async (targetId: string, token: string) => {
    if (!token.trim()) {
      return;
    }
    const ok = await saveTargetCredentials(targetId, { token: token.trim() });
    if (ok) {
      toast.success(t('credentialsSaved'));
    } else {
      toast.error(t('saveFailed'));
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

  const handleDelete = async (targetId: string) => {
    const ok = await deleteHostingTarget(targetId);
    if (ok) {
      await load();
      toast.success(t('deleted'));
    } else {
      toast.error(t('deleteFailed'));
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
          <Button onClick={() => void handleAddVercel()} disabled={saving}>
            <Plus className="h-4 w-4 mr-2" />
            {t('addVercel')}
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {targets.map((target) => (
            <div key={target.id} className="rounded-lg border p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="font-medium">{target.name}</p>
                  <p className="text-xs text-muted-foreground">{target.provider_type}{target.is_default ? ` · ${t('default')}` : ''}</p>
                </div>
                <Button variant="ghost" size="icon" onClick={() => void handleDelete(target.id)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
              {target.provider_type === 'vercel' && (
                <div className="space-y-2">
                  <Label htmlFor={`token-${target.id}`}>{t('vercelToken')}</Label>
                  <Input
                    id={`token-${target.id}`}
                    type="password"
                    placeholder={t('vercelTokenPlaceholder')}
                    onBlur={(e) => void handleSaveToken(target.id, e.target.value)}
                  />
                </div>
              )}
              {target.provider_type === 'http_webhook' && (
                <p className="text-xs text-muted-foreground">{t('webhookHint')}</p>
              )}
              <Button variant="outline" size="sm" onClick={() => void handleTest(target.id)}>
                {t('testConnection')}
              </Button>
            </div>
          ))}
          <Button variant="outline" onClick={() => void handleAddVercel()} disabled={saving}>
            <Plus className="h-4 w-4 mr-2" />
            {t('addVercel')}
          </Button>
        </div>
      )}

      <p className="text-xs text-muted-foreground">{t('providersNote')}</p>
    </div>
  );
}
