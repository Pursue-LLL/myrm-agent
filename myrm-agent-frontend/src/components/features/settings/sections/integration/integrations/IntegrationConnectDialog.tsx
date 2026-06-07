'use client';

import { memo, useState, useCallback, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { IconExternalLink } from './catalog-icons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { toast } from '@/hooks/useToast';
import useConfigStore from '@/store/useConfigStore';
import { apiRequest } from '@/lib/api';
import { buildLastScanSummary, gateMcpEnable } from '@/hooks/useMcpSecurityGate';
import { formatMcpGateBlockedMessage } from '@/lib/utils/mcpScanFindingText';
import { MCPScanAckDialog } from '@/components/features/settings/mcp/MCPScanAckDialog';
import type { MCPScanResult, MCPServiceConfig } from '@/store/config/types';
import type { CatalogEntry } from './catalog-types';

interface IntegrationConnectDialogProps {
  entry: CatalogEntry;
  locale: string;
  onClose: () => void;
  onConnected: () => void;
}

export const IntegrationConnectDialog = memo<IntegrationConnectDialogProps>(
  ({ entry, locale, onClose, onConnected }) => {
    const t = useTranslations('settings.integrationCatalog.connectDialog');
    const tSettings = useTranslations('settings');
    const hasMultiFields = entry.credentialFields && entry.credentialFields.length > 0;

    const [credential, setCredential] = useState('');
    const [fieldValues, setFieldValues] = useState<Record<string, string>>(() =>
      hasMultiFields ? Object.fromEntries(entry.credentialFields!.map((f) => [f.key, ''])) : {},
    );
    const [connecting, setConnecting] = useState(false);
    const [oauthPolling, setOauthPolling] = useState(false);
    const [pendingCatalogAck, setPendingCatalogAck] = useState<{
      config: MCPServiceConfig;
      scanResult: MCPScanResult;
      onDone: () => void;
    } | null>(null);
    const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const { mcpConfigs, setMCPConfigs } = useConfigStore();

    useEffect(() => {
      return () => {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      };
    }, []);

    const helpText = locale === 'zh' && entry.helpTextZh ? entry.helpTextZh : entry.helpText;

    const persistCatalogConfig = useCallback(
      (config: MCPServiceConfig) => {
        const exists = mcpConfigs.some((c) => c.name === config.name);
        if (!exists) {
          setMCPConfigs([...mcpConfigs, config]);
        }
        toast({ title: t('connectSuccess', { name: entry.name }) });
        onConnected();
      },
      [entry.name, mcpConfigs, onConnected, setMCPConfigs, t, toast],
    );

    const runCatalogSecurityGate = useCallback(
      async (config: MCPServiceConfig, acknowledgedHighRisks = false) => {
        const gate = await gateMcpEnable(config, { acknowledgedHighRisks });
        if (gate.needsAcknowledgement) {
          setPendingCatalogAck({
            config,
            scanResult: gate.scanResult,
            onDone: () =>
              persistCatalogConfig({
                ...config,
                lastScanSummary: buildLastScanSummary(gate.scanResult),
              }),
          });
          return false;
        }
        if (!gate.allowed) {
          toast({
            title: t('connectFailed'),
            description: formatMcpGateBlockedMessage(
              {
                verifyError: gate.verifyError,
                verifyFindings: gate.verifyFindings,
                staticFindings: gate.scanResult.findings,
                fallback: t('connectFailed'),
              },
              tSettings,
            ),
            variant: 'destructive',
          });
          return false;
        }
        persistCatalogConfig({
          ...config,
          lastScanSummary: buildLastScanSummary(gate.scanResult),
        });
        return true;
      },
      [persistCatalogConfig, t, tSettings, toast],
    );

    const handleConfirmCatalogAck = useCallback(async () => {
      if (!pendingCatalogAck) return;
      const { config } = pendingCatalogAck;
      setPendingCatalogAck(null);
      await runCatalogSecurityGate(config, true);
    }, [pendingCatalogAck, runCatalogSecurityGate]);

    const handleFieldChange = useCallback((key: string, value: string) => {
      setFieldValues((prev) => ({ ...prev, [key]: value }));
    }, []);

    const handleConnect = useCallback(async () => {
      if (entry.authType === 'oauth2') {
        setOauthPolling(true);
        try {
          const mcpCfg = entry.mcpConfig as any;
          const oauthCfg = mcpCfg?.oauth;
          if (!oauthCfg) {
            toast({ title: t('connectFailed'), description: 'Missing OAuth config', variant: 'destructive' });
            setOauthPolling(false);
            return;
          }

          // 1. Start OAuth flow
          const startRes = await apiRequest<{ authorization_url: string; state: string }>('/integrations/mcp/oauth/start', {
            method: 'POST',
            body: JSON.stringify({
              server_name: mcpCfg.name,
              authorization_endpoint: oauthCfg.authorization_endpoint,
              token_endpoint: oauthCfg.token_endpoint,
              client_id: oauthCfg.client_id,
              client_secret: oauthCfg.client_secret,
              scope: oauthCfg.scope,
              redirect_uri: `${window.location.origin}/oauth/callback`,
            }),
          });

          // 2. Open authorization URL
          if ('__TAURI__' in window) {
            const { open } = await import('@tauri-apps/plugin-shell');
            await open(startRes.authorization_url);
          } else {
            window.open(startRes.authorization_url, '_blank');
          }

          // 3. Poll for status
          pollIntervalRef.current = setInterval(async () => {
            try {
              const statusRes = await apiRequest<{ status: string }>(`/integrations/mcp/oauth/status/${startRes.state}`, { silent: true });
              if (statusRes.status === 'success') {
                if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
                
                const newConfig: MCPServiceConfig = {
                  name: mcpCfg.name,
                  type: mcpCfg.type as 'sse' | 'stdio' | 'streamable_http',
                  url: mcpCfg.url || '',
                  command: mcpCfg.command || '',
                  args: mcpCfg.args || [],
                  description: mcpCfg.description || '',
                  enabled: true,
                  extra_params: null,
                };

                if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
                setOauthPolling(false);
                await runCatalogSecurityGate(newConfig);
                return;
              } else if (statusRes.status === 'expired_or_invalid') {
                if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
                setOauthPolling(false);
                toast({ title: t('connectFailed'), description: 'OAuth session expired', variant: 'destructive' });
              }
            } catch {
              // Ignore polling errors
            }
          }, 2000);
        } catch (e) {
          setOauthPolling(false);
          toast({ title: t('connectFailed'), description: String(e), variant: 'destructive' });
        }
        return;
      }

      if (entry.authType !== 'none') {
        if (hasMultiFields) {
          const empty = entry.credentialFields!.find((f) => !fieldValues[f.key]?.trim());
          if (empty) {
            const label = locale === 'zh' && empty.labelZh ? empty.labelZh : empty.label;
            toast({ title: `${label} ${t('credentialRequired')}`, variant: 'destructive' });
            return;
          }
        } else if (!credential.trim()) {
          toast({ title: t('credentialRequired'), variant: 'destructive' });
          return;
        }
      }

      setConnecting(true);
      try {
        if (entry.connectorType === 'mcp' && entry.mcpConfig) {
          const mcpCfg = entry.mcpConfig as {
            name: string;
            type: string;
            url?: string;
            command?: string;
            args?: string[];
            env?: Record<string, string>;
            description?: string;
          };

          let finalArgs = mcpCfg.args || [];
          const envMap: Record<string, string> = { ...mcpCfg.env };

          if (hasMultiFields) {
            for (const field of entry.credentialFields!) {
              const val = fieldValues[field.key]?.trim() || '';
              if (field.inject === 'arg_placeholder') {
                finalArgs = finalArgs.map((a) => (a === field.key ? val : a));
              } else {
                envMap[field.key] = val;
              }
            }
          } else if (entry.envKey && credential.trim()) {
            envMap[entry.envKey] = credential.trim();
          }

          const newConfig: MCPServiceConfig = {
            name: mcpCfg.name,
            type: mcpCfg.type as 'sse' | 'stdio' | 'streamable_http',
            url: mcpCfg.url || '',
            command: mcpCfg.command || '',
            args: finalArgs,
            description: mcpCfg.description || '',
            enabled: true,
            extra_params: Object.keys(envMap).length > 0 ? { env: envMap } : null,
          };

          const exists = mcpConfigs.some((c) => c.name === newConfig.name);
          if (exists) {
            toast({ title: t('alreadyConnected'), variant: 'destructive' });
            setConnecting(false);
            return;
          }

          setConnecting(false);
          await runCatalogSecurityGate(newConfig);
          return;
        }
      } catch (e) {
        toast({
          title: t('connectFailed'),
          description: String(e),
          variant: 'destructive',
        });
      } finally {
        setConnecting(false);
      }
    }, [entry, credential, fieldValues, hasMultiFields, locale, mcpConfigs, setMCPConfigs, onConnected, t]);

    return (
      <>
      <Dialog open onOpenChange={(open) => !open && onClose()}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('title', { name: entry.name })}</DialogTitle>
            <DialogDescription>
              {locale === 'zh' && entry.descriptionZh ? entry.descriptionZh : entry.description}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {entry.authType === 'oauth2' ? (
              <div className="flex flex-col items-center justify-center space-y-4 py-4">
                <div className="bg-muted flex h-16 w-16 items-center justify-center rounded-2xl">
                  <IconExternalLink className="h-8 w-8 text-primary" />
                </div>
                <div className="text-center">
                  <h3 className="font-medium">{t('oauthTitle', { name: entry.name, default: `Connect to ${entry.name}` })}</h3>
                  <p className="text-muted-foreground mt-1 text-sm">{t('oauthDescription', { default: 'You will be redirected to the provider to authorize access.' })}</p>
                </div>
              </div>
            ) : entry.authType !== 'none' && (
              <>
                {hasMultiFields ? (
                  <div className="space-y-3">
                    {entry.credentialFields!.map((field) => (
                      <div key={field.key} className="space-y-1.5">
                        <Label className="text-sm">
                          {locale === 'zh' && field.labelZh ? field.labelZh : field.label}
                        </Label>
                        <Input
                          type="password"
                          value={fieldValues[field.key] || ''}
                          onChange={(e) => handleFieldChange(field.key, e.target.value)}
                          placeholder={locale === 'zh' && field.labelZh ? field.labelZh : field.label}
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Label>{t('credentialLabel')}</Label>
                    <Input
                      type="password"
                      value={credential}
                      onChange={(e) => setCredential(e.target.value)}
                      placeholder={t('credentialPlaceholder')}
                    />
                  </div>
                )}

                {helpText && <p className="text-muted-foreground text-xs">{helpText}</p>}

                {entry.helpUrl && (
                  <a
                    href={entry.helpUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary inline-flex items-center gap-1 text-xs hover:underline"
                  >
                    {t('getCredential')}
                    <IconExternalLink className="h-3 w-3" />
                  </a>
                )}
              </>
            )}
            {entry.authType === 'none' && <p className="text-muted-foreground text-sm">{t('noAuthRequired')}</p>}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t('cancel')}
            </Button>
            <Button onClick={handleConnect} disabled={connecting || oauthPolling}>
              {oauthPolling ? t('waitingAuth', { default: 'Waiting for authorization...' }) : connecting ? t('connecting') : t('connect')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <MCPScanAckDialog
        open={!!pendingCatalogAck}
        serverName={pendingCatalogAck?.config.name || ''}
        findings={pendingCatalogAck?.scanResult.findings ?? []}
        onConfirm={handleConfirmCatalogAck}
        onCancel={() => setPendingCatalogAck(null)}
      />
      </>
    );
  },
);

IntegrationConnectDialog.displayName = 'IntegrationConnectDialog';
