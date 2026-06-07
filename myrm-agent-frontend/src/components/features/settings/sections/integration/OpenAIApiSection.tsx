'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconBan, IconCheck, IconCopy, IconKey, IconPlus, IconTrash } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { toast } from '@/hooks/useToast';
import { BACKEND_BASE_URL } from '@/lib/api';
import SettingsSection from '../SettingsSection';
import ProxySettingsCard from '../system/ProxySettingsCard';
import {
  createApiKey,
  listApiKeys,
  revokeApiKey,
  deleteApiKey,
  type APIKeyInfo,
  type CreateKeyResponse,
} from '@/services/apiKeys';

const OpenAIApiSection = memo(() => {
  const t = useTranslations('settings.openaiApi');

  const [keys, setKeys] = useState<APIKeyInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newKeyResult, setNewKeyResult] = useState<CreateKeyResponse | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);

  // Form state
  const [keyName, setKeyName] = useState('');
  const [expiresInDays, setExpiresInDays] = useState<string>('');
  const [note, setNote] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  const loadKeys = useCallback(async () => {
    try {
      setIsLoading(true);
      const result = await listApiKeys();
      setKeys(result);
    } catch {
      toast({ title: 'Failed to load API keys', variant: 'destructive' });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  const handleCreate = async () => {
    if (!keyName.trim()) return;
    setIsCreating(true);
    try {
      const result = await createApiKey({
        name: keyName.trim(),
        expires_in_days: expiresInDays ? parseInt(expiresInDays) : null,
        note: note.trim() || null,
      });
      setNewKeyResult(result);
      setShowCreateForm(false);
      setKeyName('');
      setExpiresInDays('');
      setNote('');
      await loadKeys();
    } catch {
      toast({ title: 'Failed to create API key', variant: 'destructive' });
    } finally {
      setIsCreating(false);
    }
  };

  const handleCopyKey = () => {
    if (newKeyResult?.key) {
      navigator.clipboard.writeText(newKeyResult.key);
      toast({ title: t('copied') });
    }
  };

  const handleRevoke = async () => {
    if (revokeTarget === null) return;
    try {
      await revokeApiKey(revokeTarget);
      await loadKeys();
      toast({ title: 'API key revoked' });
    } catch {
      toast({ title: 'Failed to revoke key', variant: 'destructive' });
    } finally {
      setRevokeTarget(null);
    }
  };

  const handleDelete = async () => {
    if (deleteTarget === null) return;
    try {
      await deleteApiKey(deleteTarget);
      await loadKeys();
      toast({ title: 'API key deleted' });
    } catch {
      toast({ title: 'Failed to delete key', variant: 'destructive' });
    } finally {
      setDeleteTarget(null);
    }
  };

  const getKeyStatus = (key: APIKeyInfo): 'active' | 'revoked' | 'expired' => {
    if (!key.is_active) return 'revoked';
    if (key.expires_at && new Date(key.expires_at) < new Date()) return 'expired';
    return 'active';
  };

  const statusColors: Record<string, string> = {
    active: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20',
    revoked: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20',
    expired: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/20',
  };

  const apiEndpoint = `${BACKEND_BASE_URL}/v1`;

  return (
    <div className="space-y-6">
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <IconKey className="h-5 w-5" />
            {t('title')}
          </span>
        }
        description={t('description')}
        action={
          <Button onClick={() => setShowCreateForm(true)} size="sm" className="gap-1.5">
            <IconPlus className="h-4 w-4" />
            {t('createKey')}
          </Button>
        }
      >
        {/* API Endpoint info */}
        <div className="p-4 rounded-lg border border-border/50 bg-muted/30">
          <h3 className="text-sm font-medium mb-1">{t('endpoint')}</h3>
          <p className="text-xs text-muted-foreground mb-2">{t('endpointDesc')}</p>
          <code className="block p-2 rounded bg-background text-xs font-mono break-all select-all">{apiEndpoint}</code>
        </div>

        {/* Quick Start */}
        <div className="p-4 rounded-lg border border-border/50 bg-muted/30">
          <h3 className="text-sm font-medium mb-1">{t('docsTitle')}</h3>
          <p className="text-xs text-muted-foreground mb-2">{t('docsDesc')}</p>
          <pre className="p-3 rounded bg-background text-xs font-mono overflow-x-auto whitespace-pre">
            {`from openai import OpenAI

client = OpenAI(
    base_url="${apiEndpoint}",
    api_key="sk-myrm-...",
)

response = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)
for chunk in response:
    print(chunk.choices[0].delta.content, end="")`}
          </pre>
        </div>

        {/* Newly created key display */}
        {newKeyResult && (
          <div className="p-4 rounded-lg border-2 border-primary/50 bg-primary/5">
            <div className="flex items-center gap-2 mb-2">
              <IconCheck className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium">{newKeyResult.name}</span>
            </div>
            <p className="text-xs text-muted-foreground mb-2">{t('copyWarning')}</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 p-2 rounded bg-background text-xs font-mono break-all select-all">
                {newKeyResult.key}
              </code>
              <Button size="sm" variant="outline" onClick={handleCopyKey}>
                <IconCopy className="h-3.5 w-3.5" />
              </Button>
            </div>
            <Button size="sm" variant="ghost" className="mt-2 text-xs" onClick={() => setNewKeyResult(null)}>
              {t('cancel')}
            </Button>
          </div>
        )}

        {/* Create form */}
        {showCreateForm && (
          <div className="p-4 rounded-lg border border-border bg-background space-y-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('keyName')}</label>
              <input
                type="text"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                placeholder={t('keyNamePlaceholder')}
                className="mt-1 w-full h-9 px-3 rounded-full border border-input bg-background text-sm"
                autoFocus
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('expiresIn')}</label>
              <select
                value={expiresInDays}
                onChange={(e) => setExpiresInDays(e.target.value)}
                className="mt-1 w-full h-9 px-3 rounded-full border border-input bg-background text-sm"
              >
                <option value="">{t('noExpiry')}</option>
                <option value="30">30 {t('days')}</option>
                <option value="90">90 {t('days')}</option>
                <option value="180">180 {t('days')}</option>
                <option value="365">365 {t('days')}</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('note')}</label>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t('notePlaceholder')}
                className="mt-1 w-full h-9 px-3 rounded-full border border-input bg-background text-sm"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button size="sm" variant="outline" onClick={() => setShowCreateForm(false)}>
                {t('cancel')}
              </Button>
              <Button size="sm" onClick={handleCreate} disabled={!keyName.trim() || isCreating}>
                {t('create')}
              </Button>
            </div>
          </div>
        )}

        {/* Key list */}
        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Loading...</div>
        ) : keys.length === 0 ? (
          <div className="py-8 text-center space-y-2">
            <IconKey className="h-8 w-8 mx-auto text-muted-foreground/50" />
            <p className="text-sm font-medium text-muted-foreground">{t('noKeys')}</p>
            <p className="text-xs text-muted-foreground">{t('noKeysDesc')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {keys.map((key) => {
              const status = getKeyStatus(key);
              return (
                <div
                  key={key.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-lg border border-border/50 bg-background"
                >
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{key.name}</span>
                      <Badge variant="outline" className={statusColors[status]}>
                        {t(status)}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <code className="font-mono">{key.key_prefix}...</code>
                      <span>
                        {t('lastUsed')}:{' '}
                        {key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : t('never')}
                      </span>
                      <span>{t('usageCount', { count: key.usage_count })}</span>
                      <span>
                        {t('createdAt')}: {new Date(key.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    {key.note && <p className="text-xs text-muted-foreground/70 truncate">{key.note}</p>}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {status === 'active' && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-yellow-600 hover:text-yellow-700"
                        onClick={() => setRevokeTarget(key.id)}
                      >
                        <IconBan className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-destructive hover:text-destructive"
                      onClick={() => setDeleteTarget(key.id)}
                    >
                      <IconTrash className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SettingsSection>

      {/* Revoke confirmation */}
      <ConfirmDialog
        open={revokeTarget !== null}
        onOpenChange={(open) => !open && setRevokeTarget(null)}
        title={t('revoke')}
        description={t('revokeConfirm')}
        onConfirm={handleRevoke}
        confirmText={t('revoke')}
        cancelText={t('cancel')}
        variant="destructive"
      />

      {/* Delete confirmation */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={t('delete')}
        description={t('deleteConfirm')}
        onConfirm={handleDelete}
        confirmText={t('delete')}
        cancelText={t('cancel')}
        variant="destructive"
      />

      {/* LLM Passthrough Proxy */}
      <ProxySettingsCard />
    </div>
  );
});

OpenAIApiSection.displayName = 'OpenAIApiSection';

export default OpenAIApiSection;
