'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconTrash, IconAlertTriangle, IconRefresh } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { toast } from '@/lib/utils/toast';
import { fetchWithTimeout } from '@/lib/api';
import SettingsSection from '../SettingsSection';
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

interface AllowlistEntry {
  id: string;
  permission: string;
  tool_name: string | null;
  tool_args_hash: string | null;
  created_at: string;
  granularity: 'permission' | 'tool' | 'exact';
}

const AllowlistSection = memo(() => {
  const t = useTranslations('settings.securityPolicy.allowlist');
  const [entries, setEntries] = useState<AllowlistEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  const loadEntries = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchWithTimeout('/security/allowlist');
      const json = await response.json();
      if (json.success) {
        setEntries(json.data || []);
      } else {
        toast.error(t('loadError'));
      }
    } catch (error) {
      console.error('[ALLOWLIST] Load failed:', error);
      toast.error(t('loadError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  const handleDelete = useCallback(
    async (entryId: string) => {
      setDeleting(entryId);
      try {
        const response = await fetchWithTimeout(`/security/allowlist/${entryId}`, {
          method: 'DELETE',
        });
        const json = await response.json();
        if (json.success) {
          toast.success(t('deleteSuccess'));
          await loadEntries();
        } else {
          toast.error(t('deleteError'));
        }
      } catch (error) {
        console.error('[ALLOWLIST] Delete failed:', error);
        toast.error(t('deleteError'));
      } finally {
        setDeleting(null);
      }
    },
    [t, loadEntries],
  );

  const handleClearAll = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchWithTimeout('/security/allowlist', {
        method: 'DELETE',
      });
      const json = await response.json();
      if (json.success) {
        toast.success(t('clearSuccess', { count: json.data?.count || 0 }));
        setEntries([]);
      } else {
        toast.error(t('clearError'));
      }
    } catch (error) {
      console.error('[ALLOWLIST] Clear all failed:', error);
      toast.error(t('clearError'));
    } finally {
      setLoading(false);
      setShowClearConfirm(false);
    }
  }, [t]);

  const getGranularityLabel = (granularity: string) => {
    switch (granularity) {
      case 'permission':
        return t('granularity.permission');
      case 'tool':
        return t('granularity.tool');
      case 'exact':
        return t('granularity.exact');
      default:
        return granularity;
    }
  };

  const getGranularityColor = (granularity: string) => {
    switch (granularity) {
      case 'permission':
        return 'bg-amber-500/10 text-amber-600 dark:text-amber-400';
      case 'tool':
        return 'bg-blue-500/10 text-blue-600 dark:text-blue-400';
      case 'exact':
        return 'bg-green-500/10 text-green-600 dark:text-green-400';
      default:
        return 'bg-gray-500/10 text-gray-600 dark:text-gray-400';
    }
  };

  const getPermissionLabel = (permission: string) => {
    const labels: Record<string, string> = {
      code_interpreter: t('permissions.codeInterpreter'),
      shell_exec: t('permissions.shellExec'),
      file_read: t('permissions.fileRead'),
      file_write: t('permissions.fileWrite'),
      browser_navigate: t('permissions.browserNavigate'),
      browser_fill: t('permissions.browserFill'),
      browser_session: t('permissions.browserSession'),
    };
    return labels[permission] || permission;
  };

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">{t('totalEntries', { count: entries.length })}</span>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={loadEntries} disabled={loading}>
              <IconRefresh className={`mr-1 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              {t('refresh')}
            </Button>
            {entries.length > 0 && (
              <Button size="sm" variant="destructive" onClick={() => setShowClearConfirm(true)} disabled={loading}>
                <IconTrash className="mr-1 h-3.5 w-3.5" />
                {t('clearAll')}
              </Button>
            )}
          </div>
        </div>

        {entries.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground text-sm">{loading ? t('loading') : t('empty')}</div>
        ) : (
          <div className="space-y-2">
            {entries.map((entry) => (
              <div
                key={entry.id}
                className="flex items-center justify-between gap-3 p-4 rounded-lg border bg-card hover:bg-accent/5 transition-colors"
              >
                <div className="flex-1 space-y-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="font-mono text-xs">
                      {getPermissionLabel(entry.permission)}
                    </Badge>
                    <Badge className={`text-xs ${getGranularityColor(entry.granularity)}`}>
                      {getGranularityLabel(entry.granularity)}
                    </Badge>
                  </div>

                  {entry.tool_name && (
                    <div className="text-xs text-muted-foreground">
                      <span className="font-medium">{t('toolName')}:</span>{' '}
                      <span className="font-mono">{entry.tool_name}</span>
                    </div>
                  )}

                  {entry.tool_args_hash && (
                    <div className="text-xs text-muted-foreground">
                      <span className="font-medium">{t('argsHash')}:</span>{' '}
                      <span className="font-mono">{entry.tool_args_hash}</span>
                    </div>
                  )}

                  <div className="text-xs text-muted-foreground">{new Date(entry.created_at).toLocaleString()}</div>
                </div>

                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleDelete(entry.id)}
                  disabled={deleting === entry.id}
                >
                  <IconTrash className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}

        <div className="rounded-full border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 p-3 text-xs">
          <div className="flex items-start gap-2">
            <IconAlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
            <div className="space-y-1 text-amber-900 dark:text-amber-100">
              <p className="font-medium">{t('notice.title')}</p>
              <p className="text-amber-800 dark:text-amber-200">{t('notice.description')}</p>
            </div>
          </div>
        </div>
      </div>

      <AlertDialog open={showClearConfirm} onOpenChange={setShowClearConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <IconAlertTriangle className="h-5 w-5 text-destructive" />
              {t('clearConfirm.title')}
            </AlertDialogTitle>
            <AlertDialogDescription>{t('clearConfirm.description', { count: entries.length })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={loading}>{t('clearConfirm.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleClearAll}
              disabled={loading}
              className="bg-destructive hover:bg-destructive/90"
            >
              {t('clearConfirm.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  );
});

AllowlistSection.displayName = 'AllowlistSection';

export default AllowlistSection;
