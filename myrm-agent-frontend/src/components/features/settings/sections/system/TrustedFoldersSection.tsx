'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconRefresh, IconTrash, IconAlertTriangle } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { toast } from '@/lib/utils/toast';
import SettingsSection from '../SettingsSection';
import { listTrustedFolders, revokeTrustedFolder, type WorkspaceTrustEntry } from '@/services/workspaceTrust';
import { shortenHomePath } from '@/lib/directoryBrowseRecent';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';

const TrustedFoldersSection = memo(() => {
  const t = useTranslations('settings.securityPolicy.trustedFolders');
  const [entries, setEntries] = useState<WorkspaceTrustEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [confirmPath, setConfirmPath] = useState<string | null>(null);

  const loadEntries = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listTrustedFolders();
      setEntries(data);
    } catch (error) {
      console.error('[TRUSTED_FOLDERS] Load failed:', error);
      toast.error(t('loadError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadEntries();
  }, [loadEntries]);

  const handleRevoke = useCallback(
    async (path: string) => {
      setRevoking(path);
      try {
        await revokeTrustedFolder(path);
        toast.success(t('revokeSuccess'));
        await loadEntries();
      } catch (error) {
        console.error('[TRUSTED_FOLDERS] Revoke failed:', error);
        toast.error(t('revokeError'));
      } finally {
        setRevoking(null);
        setConfirmPath(null);
      }
    },
    [loadEntries, t],
  );

  const levelLabel = (level: WorkspaceTrustEntry['level']) => {
    switch (level) {
      case 'TRUSTED':
        return t('level.trusted');
      case 'RESTRICTED':
        return t('level.restricted');
      case 'REVOKED':
        return t('level.revoked');
      default:
        return level;
    }
  };

  const levelColor = (level: WorkspaceTrustEntry['level']) => {
    switch (level) {
      case 'TRUSTED':
        return 'bg-green-500/10 text-green-600 dark:text-green-400';
      case 'RESTRICTED':
        return 'bg-amber-500/10 text-amber-600 dark:text-amber-400';
      default:
        return 'bg-gray-500/10 text-gray-600 dark:text-gray-400';
    }
  };

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">{t('totalEntries', { count: entries.length })}</span>
          <Button size="sm" variant="outline" onClick={() => void loadEntries()} disabled={loading}>
            <IconRefresh className={`mr-1 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            {t('refresh')}
          </Button>
        </div>

        {entries.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">{loading ? t('loading') : t('empty')}</div>
        ) : (
          <div className="space-y-2">
            {entries.map((entry) => (
              <div
                key={entry.path}
                className="flex items-center justify-between gap-3 rounded-lg border bg-card p-4 transition-colors hover:bg-accent/5"
              >
                <div className="min-w-0 flex-1 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className={`text-xs ${levelColor(entry.level)}`}>{levelLabel(entry.level)}</Badge>
                  </div>
                  <p className="truncate font-mono text-xs text-foreground">{shortenHomePath(entry.path)}</p>
                  <p className="text-xs text-muted-foreground">{new Date(entry.decided_at).toLocaleString()}</p>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setConfirmPath(entry.path)}
                  disabled={revoking === entry.path}
                >
                  <IconTrash className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}

        <div className="rounded-full border border-amber-200 bg-amber-50 p-3 text-xs dark:border-amber-800 dark:bg-amber-950/30">
          <div className="flex items-start gap-2">
            <IconAlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400" />
            <div className="space-y-1 text-amber-900 dark:text-amber-100">
              <p className="font-medium">{t('notice.title')}</p>
              <p className="text-amber-800 dark:text-amber-200">{t('notice.description')}</p>
            </div>
          </div>
        </div>
      </div>

      <AlertDialog open={confirmPath !== null} onOpenChange={(open) => !open && setConfirmPath(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('revokeConfirm.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmPath ? t('revokeConfirm.description', { path: shortenHomePath(confirmPath) }) : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={revoking !== null}>{t('revokeConfirm.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => confirmPath && void handleRevoke(confirmPath)}
              disabled={revoking !== null}
              className="bg-destructive hover:bg-destructive/90"
            >
              {t('revokeConfirm.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  );
});

TrustedFoldersSection.displayName = 'TrustedFoldersSection';

export default TrustedFoldersSection;
