'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { ScrollArea } from '@/components/primitives/scroll-area';
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
import {
  IconPlug,
  IconLoader,
  IconTrash,
  IconAlertTriangle,
  IconRefresh,
} from '@/components/features/icons/PremiumIcons';
import { toast } from '@/hooks/shared/useToast';

interface PluginManagerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPluginChanged: () => void;
}

interface InstalledPlugin {
  name: string;
  servers: string[];
  server_meta?: InstalledServerInfo[];
  has_bundled_files: boolean;
}

interface InstalledServerInfo {
  name: string;
  enabled: boolean;
}

interface UninstallResult {
  plugin_name: string;
  removed_servers: number;
  unbound_agents: number;
  removed_files: boolean;
}

const PluginManagerDialog = memo(
  ({ open, onOpenChange, onPluginChanged }: PluginManagerDialogProps) => {
    const t = useTranslations('settings.plugins.manager');

    const [plugins, setPlugins] = useState<InstalledPlugin[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [uninstalling, setUninstalling] = useState<string | null>(null);
    const [pendingUninstall, setPendingUninstall] = useState<InstalledPlugin | null>(null);

    const refresh = useCallback(async () => {
      setIsLoading(true);
      try {
        const res = await fetch('/api/v1/plugins/import/installed');
        if (!res.ok) {
          throw new Error(`Failed to list plugins: ${res.status}`);
        }
        setPlugins((await res.json()) as InstalledPlugin[]);
      } catch (error) {
        toast({
          title: t('errors.listFailed'),
          description: error instanceof Error ? error.message : undefined,
          variant: 'destructive',
        });
      } finally {
        setIsLoading(false);
      }
    }, [t]);

    useEffect(() => {
      if (open) {
        void refresh();
      }
    }, [open, refresh]);

    const handleUninstall = useCallback(
      async (plugin: InstalledPlugin) => {
        setUninstalling(plugin.name);
        try {
          const res = await fetch(
            `/api/v1/plugins/import/${encodeURIComponent(plugin.name)}`,
            { method: 'DELETE' },
          );
          if (!res.ok) {
            const payload = (await res.json().catch(() => null)) as { detail?: unknown } | null;
            throw new Error(
              typeof payload?.detail === 'string'
                ? payload.detail
                : (t('errors.uninstallFailed') as string),
            );
          }
          const result = (await res.json()) as UninstallResult;
          setPlugins((prev) => prev.filter((item) => item.name !== plugin.name));
          toast({
            title: t('success.uninstalled'),
            description: t('success.summary', {
              servers: String(result.removed_servers),
              agents: String(result.unbound_agents),
            }),
          });
          onPluginChanged();
        } catch (error) {
          toast({
            title: t('errors.uninstallFailed'),
            description: error instanceof Error ? error.message : undefined,
            variant: 'destructive',
          });
        } finally {
          setUninstalling(null);
          setPendingUninstall(null);
        }
      },
      [t, onPluginChanged],
    );

    return (
      <>
        <Dialog open={open} onOpenChange={onOpenChange}>
          <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col p-0 overflow-hidden">
            <DialogHeader className="p-6 pb-4 border-b">
              <DialogTitle className="flex items-center gap-2 text-xl">
                <IconPlug className="w-5 h-5" />
                {t('title')}
              </DialogTitle>
              <DialogDescription>{t('subtitle')}</DialogDescription>
            </DialogHeader>

            <ScrollArea className="flex-1 px-6 bg-muted/10">
              <div className="py-6">
                {isLoading ? (
                  <div className="flex items-center justify-center py-16 text-muted-foreground">
                    <IconLoader className="w-6 h-6 animate-spin" />
                  </div>
                ) : plugins.length === 0 ? (
                  <div className="rounded-xl border border-dashed p-10 text-center">
                    <IconPlug className="w-10 h-10 mx-auto mb-4 text-muted-foreground" />
                    <p className="text-sm font-medium">{t('empty.title')}</p>
                    <p className="text-sm text-muted-foreground mt-1">{t('empty.hint')}</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {plugins.map((plugin) => (
                      <div
                        key={plugin.name}
                        className="rounded-xl border bg-background p-4 flex items-start justify-between gap-3"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="font-medium text-sm">{plugin.name}</p>
                            {plugin.has_bundled_files && (
                              <Badge variant="outline" className="text-[10px]">
                                {t('badges.bundled')}
                              </Badge>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center gap-1.5 mt-1">
                            {plugin.servers.length === 0 ? (
                              <p className="text-xs text-muted-foreground">{t('empty.servers')}</p>
                            ) : plugin.server_meta?.length ? (
                              plugin.server_meta.map((server) => (
                                <span
                                  key={server.name}
                                  className="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-1.5 py-0.5 text-xs"
                                >
                                  <span
                                    aria-hidden
                                    className={`inline-block w-1.5 h-1.5 rounded-full ${
                                      server.enabled
                                        ? 'bg-emerald-500'
                                        : 'bg-amber-500'
                                    }`}
                                  />
                                  <span className="text-muted-foreground break-all">
                                    {server.name}
                                  </span>
                                  <span
                                    className={
                                      server.enabled
                                        ? 'text-emerald-600'
                                        : 'text-amber-600'
                                    }
                                  >
                                    {server.enabled
                                      ? t('serverState.enabled')
                                      : t('serverState.disabled')}
                                  </span>
                                  {!server.enabled && (
                                    <span
                                      title={t('serverState.disabledHint')}
                                      className="cursor-help text-amber-600/80"
                                    >
                                      <IconAlertTriangle className="w-3 h-3" />
                                    </span>
                                  )}
                                </span>
                              ))
                            ) : (
                              <p className="text-xs text-muted-foreground break-all">
                                {plugin.servers.join(', ')}
                              </p>
                            )}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 shrink-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                          disabled={uninstalling !== null}
                          onClick={() => setPendingUninstall(plugin)}
                        >
                          {uninstalling === plugin.name ? (
                            <IconLoader className="w-4 h-4 animate-spin" />
                          ) : (
                            <IconTrash className="w-4 h-4" />
                          )}
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </ScrollArea>

            <div className="p-4 border-t flex items-center justify-between gap-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void refresh()}
                disabled={isLoading}
                className="gap-2"
              >
                <IconRefresh className={isLoading ? 'w-4 h-4 animate-spin' : 'w-4 h-4'} />
                {t('actions.refresh')}
              </Button>
              <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                {t('actions.close')}
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        <AlertDialog
          open={!!pendingUninstall}
          onOpenChange={(v) => !v && setPendingUninstall(null)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle className="flex items-center gap-2">
                <IconAlertTriangle className="h-5 w-5 text-destructive" />
                {t('confirm.title')}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {t('confirm.description', { name: pendingUninstall?.name ?? '' })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={uninstalling !== null}>
                {t('actions.cancel')}
              </AlertDialogCancel>
              <AlertDialogAction
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                disabled={uninstalling !== null}
                onClick={(e) => {
                  e.preventDefault();
                  if (pendingUninstall) {
                    void handleUninstall(pendingUninstall);
                  }
                }}
              >
                {t('actions.uninstall')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </>
    );
  },
);

PluginManagerDialog.displayName = 'PluginManagerDialog';

export default PluginManagerDialog;
