'use client';

import { type ElementType, memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Cable,
  Copy,
  CheckCircle2,
  XCircle,
  RefreshCw,
  ShieldAlert,
  Loader2,
  Heart,
  Unplug,
  Terminal,
  MousePointerClick,
  Wind,
  Code2,
  Sparkles,
  Share2,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
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
import { toast } from '@/hooks/useToast';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { cn } from '@/lib/utils';
import SettingsSection from '../SettingsSection';
import {
  listConnectorStatus,
  generateConnectConfig,
  runConnectDoctor,
  revokeConnect,
  type ConnectorStatus,
  type GenerateConfigResponse,
} from '@/services/connect';

type ActionState = 'idle' | 'loading';

function statusBadgeVariant(status: ConnectorStatus['status']): 'default' | 'secondary' | 'outline' {
  switch (status) {
    case 'ready':
      return 'default';
    case 'manual_config_required':
      return 'secondary';
    default:
      return 'outline';
  }
}

const AGENT_ICONS: Record<string, { icon: ElementType; color: string }> = {
  claude_code: { icon: Terminal, color: 'text-violet-500' },
  cursor: { icon: MousePointerClick, color: 'text-blue-500' },
  windsurf: { icon: Wind, color: 'text-cyan-500' },
  codex: { icon: Code2, color: 'text-emerald-500' },
  gemini_cli: { icon: Sparkles, color: 'text-amber-500' },
};

const ConnectSection = memo(() => {
  const t = useTranslations('connectWizard');
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [loading, setLoading] = useState(true);

  const [configDialog, setConfigDialog] = useState<GenerateConfigResponse | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);
  const [regenerateTarget, setRegenerateTarget] = useState<string | null>(null);
  const [actionState, setActionState] = useState<Record<string, ActionState>>({});

  const fetchStatus = useCallback(async () => {
    try {
      const data = await listConnectorStatus();
      setConnectors(data);
    } catch {
      setConnectors([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  const setAction = (profileId: string, state: ActionState) => {
    setActionState((prev) => ({ ...prev, [profileId]: state }));
  };

  const handleGenerate = useCallback(
    async (profileId: string) => {
      setAction(profileId, 'loading');
      try {
        const config = await generateConnectConfig(profileId);
        setConfigDialog(config);
        await fetchStatus();
      } catch {
        toast.error('Failed to generate config');
      } finally {
        setAction(profileId, 'idle');
      }
    },
    [fetchStatus],
  );

  const handleDoctor = useCallback(
    async (profileId: string) => {
      setAction(profileId, 'loading');
      try {
        const result = await runConnectDoctor(profileId);
        if (result.healthy) {
          toast.success(t('doctorHealthy'));
        } else {
          toast.error(t('doctorUnhealthy'));
        }
        await fetchStatus();
      } catch {
        toast.error(t('doctorUnhealthy'));
      } finally {
        setAction(profileId, 'idle');
      }
    },
    [fetchStatus, t],
  );

  const handleRevoke = useCallback(
    async (profileId: string) => {
      setAction(profileId, 'loading');
      try {
        await revokeConnect(profileId);
        toast.success(t('revoked'));
        await fetchStatus();
      } catch {
        toast.error('Failed to revoke');
      } finally {
        setAction(profileId, 'idle');
        setRevokeTarget(null);
      }
    },
    [fetchStatus, t],
  );

  const handleCopyConfig = useCallback(
    async (config: GenerateConfigResponse) => {
      const jsonStr =
        config.config_json._format === 'toml'
          ? (config.config_json._toml_snippet as string)
          : JSON.stringify(config.config_json, null, 2);
      await writeToClipboard(jsonStr, true);
      toast.success(t('copied'));
    },
    [t],
  );

  const handleCopyToken = useCallback(
    async (token: string) => {
      await writeToClipboard(token, true);
      toast.success(t('copied'));
    },
    [t],
  );

  const getConfigDisplay = (config: GenerateConfigResponse): string => {
    if (config.config_json._format === 'toml') {
      return config.config_json._toml_snippet as string;
    }
    return JSON.stringify(config.config_json, null, 2);
  };

  if (loading) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </SettingsSection>
    );
  }

  return (
    <>
      <SettingsSection
        title={
          <div className="flex items-center gap-2">
            <Cable className="h-5 w-5 text-primary" />
            {t('title')}
          </div>
        }
        description={t('description')}
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {connectors.map((connector) => {
            const isLoading = actionState[connector.profile_id] === 'loading';
            const isConnected = connector.status === 'ready';
            const isConfigured = connector.status === 'manual_config_required';
            const agentIcon = AGENT_ICONS[connector.profile_id];
            const IconComponent = agentIcon?.icon ?? Share2;
            const iconColor = agentIcon?.color ?? 'text-muted-foreground';

            return (
              <div
                key={connector.profile_id}
                className={cn(
                  'relative flex flex-col gap-3 rounded-xl border p-4 transition-all',
                  isConnected
                    ? 'border-primary/30 bg-primary/[0.03]'
                    : 'border-border/50 bg-secondary/20 hover:border-border',
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <IconComponent className={cn('h-5 w-5 shrink-0', iconColor)} />
                    <span className="font-medium text-sm">{connector.label}</span>
                  </div>
                  <Badge variant={statusBadgeVariant(connector.status)} className="text-[10px] px-1.5 py-0.5">
                    {t(`status.${connector.status}`)}
                  </Badge>
                </div>

                {connector.connected_at && (
                  <p className="text-[11px] text-muted-foreground/60">
                    {new Date(connector.connected_at).toLocaleDateString()}
                  </p>
                )}

                <div className="flex flex-wrap gap-1.5 mt-auto pt-1">
                  {!isConnected && !isConfigured && (
                    <Button
                      size="sm"
                      variant="default"
                      onClick={() => void handleGenerate(connector.profile_id)}
                      disabled={isLoading}
                      className="text-xs h-7"
                    >
                      {isLoading ? (
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      ) : (
                        <Cable className="mr-1 h-3 w-3" />
                      )}
                      {t('generate')}
                    </Button>
                  )}

                  {(isConnected || isConfigured) && (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setRegenerateTarget(connector.profile_id)}
                        disabled={isLoading}
                        className="text-xs h-7"
                      >
                        {isLoading ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <RefreshCw className="mr-1 h-3 w-3" />
                        )}
                        {t('regenerate')}
                      </Button>

                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void handleDoctor(connector.profile_id)}
                        disabled={isLoading}
                        className="text-xs h-7"
                      >
                        <Heart className="mr-1 h-3 w-3" />
                        {t('doctor')}
                      </Button>

                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setRevokeTarget(connector.profile_id)}
                        disabled={isLoading}
                        className="text-xs h-7 text-destructive hover:text-destructive"
                      >
                        <Unplug className="mr-1 h-3 w-3" />
                        {t('revoke')}
                      </Button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </SettingsSection>

      {/* Config Generate Dialog */}
      <Dialog open={configDialog !== null} onOpenChange={(open) => !open && setConfigDialog(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-primary" />
              {t('configReady')}
            </DialogTitle>
            <DialogDescription>{t('configReadyDesc')}</DialogDescription>
          </DialogHeader>

          {configDialog && (
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">{t('configFile')}</label>
                <pre className="relative rounded-lg bg-secondary/60 p-3 text-xs font-mono overflow-x-auto max-h-48 border border-border/30">
                  {getConfigDisplay(configDialog)}
                </pre>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void handleCopyConfig(configDialog)}
                  className="text-xs h-7"
                >
                  <Copy className="mr-1 h-3 w-3" />
                  {t('copyConfig')}
                </Button>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">{t('token')}</label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded bg-secondary/60 px-2 py-1 text-xs font-mono truncate border border-border/30">
                    {configDialog.token}
                  </code>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void handleCopyToken(configDialog.token)}
                    className="text-xs h-7 shrink-0"
                  >
                    <Copy className="mr-1 h-3 w-3" />
                    {t('copy')}
                  </Button>
                </div>
                <p className="flex items-center gap-1 text-[11px] text-amber-500">
                  <ShieldAlert className="h-3 w-3 shrink-0" />
                  {t('tokenWarning')}
                </p>
              </div>

              <div className="rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground leading-relaxed">
                {configDialog.instructions}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setConfigDialog(null)}>
              {t('close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Regenerate Confirm Dialog */}
      <AlertDialog open={regenerateTarget !== null} onOpenChange={(open) => !open && setRegenerateTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <RefreshCw className="h-5 w-5 text-primary" />
              {t('regenerate')}
            </AlertDialogTitle>
            <AlertDialogDescription>{t('regenerateConfirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('close')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (regenerateTarget) {
                  setRegenerateTarget(null);
                  void handleGenerate(regenerateTarget);
                }
              }}
            >
              {t('regenerate')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Revoke Confirm Dialog */}
      <AlertDialog open={revokeTarget !== null} onOpenChange={(open) => !open && setRevokeTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-destructive" />
              {t('revoke')}
            </AlertDialogTitle>
            <AlertDialogDescription>{t('revokeConfirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('close')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => revokeTarget && void handleRevoke(revokeTarget)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('revoke')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
});

ConnectSection.displayName = 'ConnectSection';

export default ConnectSection;
