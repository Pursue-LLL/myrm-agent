'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconKey, IconPlus, IconTrash, IconLoader, IconEdit } from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { listAgentSecrets, createOrUpdateAgentSecret, deleteAgentSecret } from '@/services/agent';
import { toast } from '@/hooks/useToast';

interface AgentSecretsTabProps {
  agentId: string | null;
  isNew?: boolean;
}

function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return 'Unknown error';
}

export function AgentSecretsTab({ agentId, isNew }: AgentSecretsTabProps) {
  const t = useTranslations();
  const [secrets, setSecrets] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [secretValue, setSecretValue] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const fetchSecrets = useCallback(async () => {
    if (!agentId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listAgentSecrets(agentId);
      setSecrets(data);
    } catch (err: unknown) {
      console.error('Failed to fetch secrets:', err);
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    if (agentId && !isNew) {
      fetchSecrets();
    }
  }, [agentId, isNew, fetchSecrets]);

  const handleSave = async () => {
    if (!agentId) return;
    if (!keyName.trim() || !secretValue.trim()) {
      toast.warning(t('agent.secrets.validationError', { fallback: 'Key and Value are required.' }));
      return;
    }

    setIsSubmitting(true);
    try {
      await createOrUpdateAgentSecret(agentId, {
        key_name: keyName.trim(),
        secret_value: secretValue.trim(),
      });
      setKeyName('');
      setSecretValue('');
      setIsFormOpen(false);
      setIsEditing(false);
      await fetchSecrets();
    } catch (err: unknown) {
      console.error('Failed to save secret:', err);
      toast.error(t('agent.secrets.saveError', { fallback: 'Failed to save secret.' }));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteConfirm = useCallback(async () => {
    if (!agentId || !deleteTarget) return;

    try {
      await deleteAgentSecret(agentId, deleteTarget);
      await fetchSecrets();
    } catch (err: unknown) {
      console.error('Failed to delete secret:', err);
      toast.error(t('agent.secrets.deleteError', { fallback: 'Failed to delete secret.' }));
      throw err;
    } finally {
      setDeleteTarget(null);
    }
  }, [agentId, deleteTarget, fetchSecrets, t]);

  const openAddForm = () => {
    setKeyName('');
    setSecretValue('');
    setIsEditing(false);
    setIsFormOpen(true);
  };

  const openEditForm = (key: string) => {
    setKeyName(key);
    setSecretValue('');
    setIsEditing(true);
    setIsFormOpen(true);
  };

  if (isNew) {
    return (
      <div className="rounded-2xl border border-border/50 bg-card p-8 text-center">
        <IconKey className="mx-auto h-12 w-12 text-muted-foreground/50 mb-4" />
        <h3 className="text-lg font-medium text-foreground mb-2">
          {t('agent.secrets.saveFirstTitle', { fallback: 'Save Agent First' })}
        </h3>
        <p className="text-sm text-muted-foreground">
          {t('agent.secrets.saveFirstDesc', {
            fallback: 'You must save the agent before adding secrets.',
          })}
        </p>
      </div>
    );
  }

  return (
    <div className={cn('rounded-2xl border border-border/50 bg-card', 'animate-in fade-in-50 duration-300')}>
      <div className="p-6 border-b border-border/50 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium text-foreground flex items-center gap-2">
            <IconKey className="h-5 w-5 text-primary" />
            {t('agent.secrets.title', { fallback: 'Agent Secrets' })}
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            {t('agent.secrets.description', {
              fallback: 'Manage environment variables and API keys securely injected into the agent.',
            })}
          </p>
        </div>
        {!isFormOpen && (
          <Button onClick={openAddForm} size="sm" className="gap-2">
            <IconPlus className="h-4 w-4" />
            {t('agent.secrets.addBtn', { fallback: 'Add Secret' })}
          </Button>
        )}
      </div>

      <div className="p-6">
        {isFormOpen && (
          <div className="mb-6 p-4 rounded-xl border border-primary/20 bg-primary/5 space-y-4">
            <h4 className="text-sm font-medium text-foreground">
              {isEditing
                ? t('agent.secrets.editSecret', { fallback: 'Update Secret' })
                : t('agent.secrets.addSecret', { fallback: 'New Secret' })}
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-xs font-medium text-foreground">
                  {t('agent.secrets.keyName', { fallback: 'Key Name' })}
                </label>
                <Input
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''))}
                  placeholder="e.g. API_KEY"
                  disabled={isEditing}
                  className="bg-background"
                />
                <p className="text-[10px] text-muted-foreground">
                  {t('agent.secrets.keyHint', {
                    fallback: 'Uppercase letters, numbers, and underscores only.',
                  })}
                </p>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium text-foreground">
                  {t('agent.secrets.secretValue', { fallback: 'Secret Value' })}
                </label>
                <Input
                  type="password"
                  value={secretValue}
                  onChange={(e) => setSecretValue(e.target.value)}
                  placeholder={
                    isEditing
                      ? t('agent.secrets.newValuePlaceholder', {
                          fallback: 'Enter new value to overwrite',
                        })
                      : t('agent.secrets.valuePlaceholder', { fallback: 'Enter secret value' })
                  }
                  className="bg-background"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" size="sm" onClick={() => setIsFormOpen(false)} disabled={isSubmitting}>
                {t('common.cancel', { fallback: 'Cancel' })}
              </Button>
              <Button size="sm" onClick={handleSave} disabled={isSubmitting}>
                {isSubmitting && <IconLoader className="mr-2 h-3 w-3 animate-spin" />}
                {t('common.save', { fallback: 'Save' })}
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-8">
            <IconLoader className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="text-center py-8 text-destructive text-sm bg-destructive/10 rounded-xl">{error}</div>
        ) : secrets.length === 0 && !isFormOpen ? (
          <div className="text-center py-12 border-2 border-dashed border-border/50 rounded-xl">
            <IconKey className="mx-auto h-8 w-8 text-muted-foreground/30 mb-3" />
            <p className="text-sm text-muted-foreground">
              {t('agent.secrets.empty', { fallback: 'No secrets configured yet.' })}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {secrets.map((key) => (
              <div
                key={key}
                className="flex items-center justify-between p-3 rounded-xl border border-border/50 bg-background hover:bg-muted/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
                    <IconKey className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground font-mono">{key}</p>
                    <p className="text-xs text-muted-foreground">••••••••••••••••</p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-foreground"
                    onClick={() => openEditForm(key)}
                  >
                    <IconEdit className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={() => setDeleteTarget(key)}
                  >
                    <IconTrash className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={t('agent.secrets.deleteTitle', { fallback: 'Delete Secret' })}
        description={t('agent.secrets.deleteDesc', {
          fallback: `Are you sure you want to delete "${deleteTarget}"? This action cannot be undone.`,
        })}
        confirmText={t('agent.secrets.deleteBtn', { fallback: 'Delete' })}
        cancelText={t('common.cancel', { fallback: 'Cancel' })}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
}
