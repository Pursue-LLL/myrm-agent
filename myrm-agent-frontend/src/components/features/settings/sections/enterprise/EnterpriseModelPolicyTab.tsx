'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { IconPlus, IconTrash } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { getApiUrl } from '@/lib/api';

interface PolicyEntry {
  id: string;
  pattern: string;
  description: string;
  created_by: string;
  created_at: number;
}

const EnterpriseModelPolicyTab = memo(() => {
  const t = useTranslations('settings.enterprise');
  const [policies, setPolicies] = useState<PolicyEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [newPattern, setNewPattern] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [adding, setAdding] = useState(false);

  const orgId = typeof window !== 'undefined' ? localStorage.getItem('org_id') || '' : '';

  const fetchPolicies = useCallback(async () => {
    if (!orgId) {
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(getApiUrl(`/api/enterprise/org/${orgId}/model-policy`));
      if (res.ok) {
        const data = await res.json();
        setPolicies(data.patterns || []);
      }
    } catch {
      toast.error(t('modelPolicy.loadFailed', { default: 'Failed to load model policy' }));
    } finally {
      setLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void fetchPolicies();
  }, [fetchPolicies]);

  const warnFanoutPartial = (failed: number) => {
    if (failed <= 0) {
      return;
    }
    toast.warning(
      t('modelPolicy.fanoutPartial', {
        default:
          'Policy saved, but {failed} member sandbox(es) did not sync. Active members may need to refresh.',
        failed: String(failed),
      }),
    );
  };

  const handleAdd = async () => {
    if (!newPattern.trim() || !orgId) return;
    setAdding(true);
    try {
      const res = await fetch(getApiUrl(`/api/enterprise/org/${orgId}/model-policy`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pattern: newPattern.trim(), description: newDescription.trim() }),
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const saved = (await res.json()) as { fanout?: { failed?: number } };
      toast.success(t('modelPolicy.added', { default: 'Model policy updated' }));
      warnFanoutPartial(saved.fanout?.failed ?? 0);
      setNewPattern('');
      setNewDescription('');
      await fetchPolicies();
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t('modelPolicy.addFailed', { default: 'Failed to update model policy' }),
      );
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (entryId: string) => {
    if (!orgId) return;
    try {
      const res = await fetch(getApiUrl(`/api/enterprise/org/${orgId}/model-policy/${entryId}`), {
        method: 'DELETE',
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const saved = (await res.json()) as { fanout?: { failed?: number } };
      toast.success(t('modelPolicy.removed', { default: 'Pattern removed' }));
      warnFanoutPartial(saved.fanout?.failed ?? 0);
      await fetchPolicies();
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t('modelPolicy.removeFailed', { default: 'Failed to remove pattern' }),
      );
    }
  };

  if (loading) {
    return <div className="animate-pulse h-32 bg-muted rounded" />;
  }

  if (!orgId) {
    return (
      <div className="text-center text-muted-foreground py-8">
        {t('modelPolicy.noOrg', { default: 'Organization not configured' })}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-sm font-medium">
          {t('modelPolicy.title', { default: 'Allowed Models' })}
        </h3>
        <p className="text-xs text-muted-foreground">
          {t('modelPolicy.description', {
            default:
              'Define which models members can use. Supports patterns like openai/*, deepseek/*, or claude/*. Empty list = no restriction.',
          })}
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
        <div className="flex-1 space-y-1">
          <Input
            value={newPattern}
            onChange={(e) => setNewPattern(e.target.value)}
            placeholder="e.g. openai/*, deepseek/*, claude/*"
            className="text-sm"
          />
        </div>
        <div className="flex-1 space-y-1">
          <Input
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            placeholder={t('modelPolicy.descPlaceholder', { default: 'Description (optional)' })}
            className="text-sm"
          />
        </div>
        <Button
          size="sm"
          onClick={handleAdd}
          disabled={!newPattern.trim() || adding}
          className="w-full sm:w-auto"
        >
          <IconPlus className="h-3.5 w-3.5 mr-1" />
          {t('modelPolicy.add', { default: 'Add' })}
        </Button>
      </div>

      {policies.length === 0 ? (
        <div className="text-center text-muted-foreground py-6 border border-dashed border-border rounded-lg">
          {t('modelPolicy.empty', { default: 'No model restrictions. All models are accessible.' })}
        </div>
      ) : (
        <div className="border border-border rounded-lg divide-y divide-border">
          {policies.map((entry) => (
            <div key={entry.id} className="flex items-center justify-between px-4 py-3">
              <div className="flex-1 min-w-0">
                <code className="text-sm font-mono bg-muted px-2 py-0.5 rounded">
                  {entry.pattern}
                </code>
                {entry.description && (
                  <span className="ml-3 text-xs text-muted-foreground">{entry.description}</span>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleRemove(entry.id)}
                className="text-destructive hover:text-destructive/80"
              >
                <IconTrash className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {policies.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {t('modelPolicy.note', {
            default: 'Members can only use models matching the patterns above. Changes apply immediately.',
          })}
        </p>
      )}
    </div>
  );
});

EnterpriseModelPolicyTab.displayName = 'EnterpriseModelPolicyTab';

export default EnterpriseModelPolicyTab;
