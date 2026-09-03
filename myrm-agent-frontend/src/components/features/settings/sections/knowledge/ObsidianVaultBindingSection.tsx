'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { IconFolder, IconRefresh, IconCheck, IconTrash } from '@/components/features/icons/PremiumIcons';
import { wikiService } from '@/services/wikiService';

interface ObsidianVaultBindingSectionProps {
  agentScopeId?: string | null;
}

export function ObsidianVaultBindingSection({ agentScopeId }: ObsidianVaultBindingSectionProps) {
  const t = useTranslations('settings.wiki.obsidianBinding');
  const [vaultPath, setVaultPath] = useState('');
  const [isBound, setIsBound] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [lastWatermark, setLastWatermark] = useState<number>(0);

  const fetchBinding = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await wikiService.getObsidianVaultBinding();
      if (res && res.is_bound) {
        setIsBound(true);
        setVaultPath(res.vault_path);
        setLastWatermark(res.last_sync_watermark);
      } else {
        setIsBound(false);
        setVaultPath('');
      }
    } catch (err) {
      console.error('Failed to get Obsidian vault binding:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchBinding();
  }, [fetchBinding]);

  const handleBind = useCallback(async () => {
    if (!vaultPath.trim()) return;
    try {
      setIsSaving(true);
      const res = await wikiService.bindObsidianVault({
        vault_path: vaultPath.trim(),
        auto_sync_on_recall: true,
        allow_inbox_write: true,
      });
      setIsBound(res.is_bound);
      setLastWatermark(res.last_sync_watermark);
      toast.success(t('bindSuccess'));
    } catch (err) {
      console.error('Failed to bind vault:', err);
      toast.error(t('bindFailed'));
    } finally {
      setIsSaving(false);
    }
  }, [vaultPath, t]);

  const handleUnbind = useCallback(async () => {
    try {
      setIsSaving(true);
      await wikiService.unbindObsidianVault();
      setIsBound(false);
      setVaultPath('');
      toast.success(t('unbindSuccess'));
    } catch (err) {
      console.error('Failed to unbind vault:', err);
      toast.error(t('unbindFailed'));
    } finally {
      setIsSaving(false);
    }
  }, [t]);

  const handleSyncDelta = useCallback(async () => {
    try {
      setIsSyncing(true);
      const res = await wikiService.syncObsidianVaultDelta(agentScopeId);
      if (res.success) {
        setLastWatermark(res.new_watermark);
        toast.success(res.message || t('syncSuccess'));
      } else {
        toast.error(t('syncFailed'));
      }
    } catch (err) {
      console.error('Failed to sync vault delta:', err);
      toast.error(t('syncFailed'));
    } finally {
      setIsSyncing(false);
    }
  }, [agentScopeId, t]);

  return (
    <Card id="wiki-obsidian-vault-binding" data-testid="wiki-obsidian-vault-binding">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconFolder className="w-5 h-5 text-purple-600 dark:text-purple-400" />
          {t('title')}
        </CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="text-xs text-muted-foreground">{t('loading')}</div>
        ) : isBound ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded-lg border bg-muted/40 p-3">
              <div className="space-y-1 overflow-hidden pr-2">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center rounded-md bg-green-500/10 text-green-600 dark:text-green-400 px-2 py-0.5 text-xs font-medium">
                    <IconCheck className="w-3.5 h-3.5 mr-1" />
                    {t('statusBound')}
                  </span>
                </div>
                <div className="font-mono text-xs text-foreground truncate" title={vaultPath}>
                  {vaultPath}
                </div>
                {lastWatermark > 0 && (
                  <div className="text-[11px] text-muted-foreground">
                    {t('watermarkLabel')}: {new Date(lastWatermark * 1000).toLocaleString()}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button variant="outline" size="sm" disabled={isSyncing} onClick={() => void handleSyncDelta()}>
                  <IconRefresh className={`w-3.5 h-3.5 mr-1.5 ${isSyncing ? 'animate-spin' : ''}`} />
                  {isSyncing ? t('syncing') : t('syncDelta')}
                </Button>
                <Button variant="ghost" size="sm" disabled={isSaving} onClick={() => void handleUnbind()}>
                  <IconTrash className="w-3.5 h-3.5 text-destructive" />
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">{t('boundHint')}</p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                placeholder={t('pathPlaceholder')}
                value={vaultPath}
                onChange={(e) => setVaultPath(e.target.value)}
                className="font-mono text-xs"
              />
              <Button
                variant="default"
                size="sm"
                disabled={!vaultPath.trim() || isSaving}
                onClick={() => void handleBind()}
              >
                {isSaving ? t('binding') : t('bindButton')}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">{t('unboundHint')}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
