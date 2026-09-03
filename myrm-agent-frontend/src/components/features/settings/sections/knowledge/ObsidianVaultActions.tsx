'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { IconDatabase, IconExplore } from '@/components/features/icons/PremiumIcons';
import { wikiService } from '@/services/wikiService';
import { isLocalMode, isTauriRuntime } from '@/lib/deploy-mode';
import { ObsidianVaultBindingSection } from './ObsidianVaultBindingSection';

interface ObsidianVaultActionsProps {
  agentScopeId?: string | null;
  wikiPath?: string;
  vaultReady: boolean;
  obsidianLaunchAvailable?: boolean;
  vaultGitEnabled?: boolean;
  vaultGitInitialized?: boolean;
  vaultGitLastCommit?: string | null;
}

export function ObsidianVaultActions({
  agentScopeId,
  wikiPath,
  vaultReady,
  obsidianLaunchAvailable = false,
  vaultGitEnabled = false,
  vaultGitInitialized = false,
  vaultGitLastCommit = null,
}: ObsidianVaultActionsProps) {
  const t = useTranslations('settings.wiki.obsidianVault');
  const [isExporting, setIsExporting] = useState(false);
  const [isRevealing, setIsRevealing] = useState(false);
  const [isOpeningObsidian, setIsOpeningObsidian] = useState(false);
  const showLocalActions = isLocalMode() || isTauriRuntime();

  const handleCopyPath = useCallback(async () => {
    if (!wikiPath) {
      return;
    }
    try {
      await navigator.clipboard.writeText(wikiPath);
      toast.success(t('copyPathSuccess'));
    } catch {
      toast.error(t('copyPathFailed'));
    }
  }, [t, wikiPath]);

  const handleReveal = useCallback(async () => {
    setIsRevealing(true);
    try {
      if (isTauriRuntime() && wikiPath) {
        const { open } = await import('@tauri-apps/plugin-shell');
        await open(wikiPath);
        toast.success(t('revealSuccess'));
        return;
      }
      await wikiService.revealWikiVault(agentScopeId);
      toast.success(t('revealSuccess'));
    } catch (error) {
      console.error('Failed to reveal wiki vault:', error);
      toast.error(t('revealFailed'));
    } finally {
      setIsRevealing(false);
    }
  }, [agentScopeId, t, wikiPath]);

  const handleOpenObsidian = useCallback(async () => {
    setIsOpeningObsidian(true);
    try {
      await wikiService.openWikiVaultInObsidian(agentScopeId);
      toast.success(t('openObsidianSuccess'));
    } catch (error) {
      console.error('Failed to open wiki vault in Obsidian:', error);
      toast.error(t('openObsidianFailed'));
    } finally {
      setIsOpeningObsidian(false);
    }
  }, [agentScopeId, t]);

  const handleExport = useCallback(async () => {
    setIsExporting(true);
    try {
      await wikiService.exportVault(agentScopeId);
      toast.success(t('exportSuccess'));
    } catch (error) {
      console.error('Wiki Obsidian export failed:', error);
      toast.error(t('exportFailed'));
    } finally {
      setIsExporting(false);
    }
  }, [agentScopeId, t]);

  return (
    <>
    <Card id="wiki-obsidian-vault-actions">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconExplore className="w-5 h-5" />
          {t('title')}
        </CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">{t('mountHint')}</p>
        {vaultGitEnabled && vaultGitInitialized && (
          <p className="text-xs text-muted-foreground">
            {vaultGitLastCommit ? t('gitHistoryHintWithCommit', { commit: vaultGitLastCommit }) : t('gitHistoryHint')}
          </p>
        )}
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          {showLocalActions && (
            <>
              {obsidianLaunchAvailable && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!vaultReady || isOpeningObsidian}
                  onClick={() => void handleOpenObsidian()}
                >
                  {isOpeningObsidian ? t('opening') : t('openObsidian')}
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                disabled={!vaultReady || isRevealing}
                onClick={() => void handleReveal()}
              >
                {isRevealing ? t('opening') : t('revealFolder')}
              </Button>
              <Button variant="ghost" size="sm" disabled={!wikiPath} onClick={() => void handleCopyPath()}>
                {t('copyPath')}
              </Button>
            </>
          )}
          <Button variant="default" size="sm" disabled={!vaultReady || isExporting} onClick={() => void handleExport()}>
            <IconDatabase className="w-4 h-4 mr-2" />
            {isExporting ? t('exporting') : t('downloadPack')}
          </Button>
        </div>
        {!showLocalActions && <p className="text-xs text-muted-foreground">{t('cloudHint')}</p>}
      </CardContent>
    </Card>
    <ObsidianVaultBindingSection agentScopeId={agentScopeId} />
    </>
  );
}
