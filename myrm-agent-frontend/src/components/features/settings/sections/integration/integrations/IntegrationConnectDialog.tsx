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
import { apiRequest, BACKEND_BASE_URL } from '@/lib/api';
import { buildLastScanSummary, gateMcpEnable } from '@/hooks/useMcpSecurityGate';
import { formatMcpGateBlockedMessage } from '@/lib/utils/mcpScanFindingText';
import { MCPScanAckDialog } from '@/components/features/settings/mcp/MCPScanAckDialog';
import type { MCPScanResult, MCPServiceConfig } from '@/store/config/types';
import { getDocsUrl, isSandbox } from '@/lib/deploy-mode';
import type { CatalogEntry } from './catalog-types';
import { shouldBlockCloudLoopbackConnect, shouldBlockLocalOnlyInSandbox } from './deploymentGuard';

interface IntegrationConnectDialogProps {
  entry: CatalogEntry;
  locale: string;
  onClose: () => void;
  onConnected: () => void;
}

interface CatalogOAuthConfig {
  authorization_endpoint: string;
  token_endpoint: string;
  client_id: string;
  client_secret: string;
  scope?: string;
}

interface CatalogMcpDialogConfig {
  name: string;
  type: 'sse' | 'stdio' | 'streamable_http';
  url?: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  headers?: Record<string, string>;
  description?: string;
  oauth?: CatalogOAuthConfig;
}

type ProbeRecommendedMode =
  | 'local_or_tauri'
  | 'start_local_editor_mcp'
  | 'verify_local_network_and_editor';

type ProbeReasonCode =
  | 'reachable'
  | 'connection_refused'
  | 'connection_unreachable'
  | 'tls_verification_failed'
  | 'connection_timeout'
  | 'probe_failed_unknown'
  | 'loopback_unavailable_in_cloud';

function normalizeProbeRecommendedMode(value: string | undefined): ProbeRecommendedMode | null {
  if (value === 'local_or_tauri' || value === 'start_local_editor_mcp' || value === 'verify_local_network_and_editor') {
    return value;
  }
  return null;
}

function normalizeProbeReasonCode(value: string | undefined): ProbeReasonCode | null {
  if (
    value === 'reachable' ||
    value === 'connection_refused' ||
    value === 'connection_unreachable' ||
    value === 'tls_verification_failed' ||
    value === 'connection_timeout' ||
    value === 'probe_failed_unknown' ||
    value === 'loopback_unavailable_in_cloud'
  ) {
    return value;
  }
  return null;
}

function probeErrorI18nKey(
  reasonCode: ProbeReasonCode | null,
):
  | 'probeConnectionRefused'
  | 'probeConnectionUnreachable'
  | 'probeTlsVerificationFailed'
  | 'probeConnectionTimeout'
  | 'probeUnknownFailure'
  | null {
  if (reasonCode === 'connection_refused') {
    return 'probeConnectionRefused';
  }
  if (reasonCode === 'connection_unreachable') {
    return 'probeConnectionUnreachable';
  }
  if (reasonCode === 'tls_verification_failed') {
    return 'probeTlsVerificationFailed';
  }
  if (reasonCode === 'connection_timeout') {
    return 'probeConnectionTimeout';
  }
  if (reasonCode === 'probe_failed_unknown') {
    return 'probeUnknownFailure';
  }
  return null;
}

function resolveProbeUrl(mcpConfig: Record<string, unknown> | null): string | undefined {
  const probeUrlCandidate = mcpConfig?.probeUrl;
  if (typeof probeUrlCandidate === 'string' && probeUrlCandidate.trim()) {
    return probeUrlCandidate;
  }
  const urlCandidate = mcpConfig?.url;
  if (typeof urlCandidate === 'string' && urlCandidate.trim()) {
    return urlCandidate;
  }
  return undefined;
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
    const [probeStatus, setProbeStatus] = useState<'idle' | 'probing' | 'reachable' | 'unreachable' | 'cloud_not_supported'>('idle');
    const [probeError, setProbeError] = useState<string | null>(null);
    const [probeRecommendedMode, setProbeRecommendedMode] = useState<ProbeRecommendedMode | null>(null);
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
    const connectGuide = locale === 'zh' && entry.postConnectGuideZh ? entry.postConnectGuideZh : entry.postConnectGuide;
    const mcpConfig = entry.mcpConfig as Record<string, unknown> | null;
    const probeUrl = resolveProbeUrl(mcpConfig);
    const deploymentScope =
      entry.deploymentScope ??
      ((mcpConfig?.deploymentScope as string | undefined) ?? null);
    const isLocalTauriOnlyEntry = deploymentScope === 'local_tauri_only';
    const isSandboxMode = isSandbox();

    const runProbe = useCallback(async () => {
      if (!probeUrl) return true;
      setProbeStatus('probing');
      setProbeError(null);
      setProbeRecommendedMode(null);
      try {
        const res = await apiRequest<{
          status: string;
          error?: string;
          reasonCode?: string;
          recommendedMode?: string;
          shouldBlockConnect?: boolean;
        }>('/integrations/mcp/probe', {
          method: 'POST',
          body: JSON.stringify({ url: probeUrl, timeout: 5 }),
        });
        if (res.status === 'reachable') {
          setProbeStatus('reachable');
          setProbeRecommendedMode(null);
          return true;
        }
        if (res.status === 'cloud_not_supported') {
          const nextMode = normalizeProbeRecommendedMode(res.recommendedMode) ?? 'local_or_tauri';
          setProbeStatus('cloud_not_supported');
          if (res.shouldBlockConnect === true) {
            setProbeError(t('probeCloudLoopbackBlocked'));
            setProbeRecommendedMode(nextMode);
            return false;
          }
          if (
            shouldBlockCloudLoopbackConnect({
              status: res.status,
              isSandboxMode,
              isLocalTauriOnlyEntry,
            })
          ) {
            setProbeError(t('probeCloudLoopbackBlocked'));
            setProbeRecommendedMode(nextMode);
            return false;
          }
          setProbeRecommendedMode(null);
          return true;
        }
        setProbeStatus('unreachable');
        setProbeRecommendedMode(normalizeProbeRecommendedMode(res.recommendedMode));
        const reasonCode = normalizeProbeReasonCode(res.reasonCode);
        const errorKey = probeErrorI18nKey(reasonCode);
        setProbeError(
          errorKey
            ? t(errorKey)
            : t('probeUnknownFailure', {
                default: t('probeUnreachable'),
              }),
        );
        return false;
      } catch {
        setProbeStatus('unreachable');
        setProbeRecommendedMode(null);
        setProbeError(t('probeUnreachable'));
        return false;
      }
    }, [isLocalTauriOnlyEntry, isSandboxMode, probeUrl, t]);

    const persistCatalogConfig = useCallback(
      (config: MCPServiceConfig) => {
        const finalConfig: MCPServiceConfig = {
          ...config,
          hostSerial: mcpConfig?.hostSerial === true ? true : config.hostSerial,
          keepaliveInterval:
            typeof mcpConfig?.keepaliveInterval === 'number' ? mcpConfig.keepaliveInterval : config.keepaliveInterval,
        };
        const exists = mcpConfigs.some((c) => c.name === finalConfig.name);
        if (!exists) {
          setMCPConfigs([...mcpConfigs, finalConfig]);
        }
        toast({ title: t('connectSuccess', { name: entry.name }) });
        onConnected();
      },
      [entry.name, mcpConfig, mcpConfigs, onConnected, setMCPConfigs, t, toast],
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

    const handleConnect = useCallback(async (options?: { skipProbe?: boolean }) => {
      if (entry.authType === 'oauth2') {
        setOauthPolling(true);
        try {
          const mcpCfg = entry.mcpConfig as CatalogMcpDialogConfig | null;
          const oauthCfg = mcpCfg?.oauth;
          if (!mcpCfg || !oauthCfg) {
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
              redirect_uri: `${BACKEND_BASE_URL || window.location.origin}/api/v1/integrations/mcp/oauth/callback`,
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

      if (
        shouldBlockLocalOnlyInSandbox({
          isSandboxMode,
          isLocalTauriOnlyEntry,
        })
      ) {
        setProbeStatus('cloud_not_supported');
        setProbeError(t('probeCloudLoopbackBlocked'));
        setProbeRecommendedMode('local_or_tauri');
        return;
      }

      setConnecting(true);
      try {
        if (entry.connectorType === 'mcp' && entry.mcpConfig) {
          // Run connectivity probe if available
          if (probeUrl && options?.skipProbe !== true) {
            const probeOk = await runProbe();
            if (!probeOk) {
              setConnecting(false);
              return;
            }
          }

          const mcpCfg = entry.mcpConfig as CatalogMcpDialogConfig;

          let finalArgs = mcpCfg.args || [];
          const envMap: Record<string, string> = { ...mcpCfg.env };
          const headerMap: Record<string, string> = { ...mcpCfg.headers };

          if (hasMultiFields) {
            for (const field of entry.credentialFields!) {
              const val = fieldValues[field.key]?.trim() || '';
              if (field.inject === 'arg_placeholder') {
                finalArgs = finalArgs.map((a) => (a === field.key ? val : a));
              } else if (field.inject === 'header') {
                headerMap[field.key] = val;
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
            headers: Object.keys(headerMap).length > 0 ? headerMap : null,
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
    }, [entry, credential, fieldValues, hasMultiFields, isLocalTauriOnlyEntry, isSandboxMode, locale, mcpConfigs, setMCPConfigs, onConnected, t, probeUrl, runProbe]);

    const handleProbeRecommendedAction = useCallback(async () => {
      if (probeRecommendedMode === 'local_or_tauri') {
        const localDeploymentGuideUrl = getDocsUrl('/getting-started/local-deployment');
        const opened = window.open(localDeploymentGuideUrl, '_blank', 'noopener,noreferrer');
        if (!opened) {
          window.location.assign(localDeploymentGuideUrl);
        }
        onClose();
        return;
      }
      const probeOk = await runProbe();
      if (!probeOk) {
        return;
      }
      await handleConnect({ skipProbe: true });
    }, [handleConnect, onClose, probeRecommendedMode, runProbe]);

    const probeRecommendedMessage =
      probeRecommendedMode === 'local_or_tauri'
        ? t('probeRecommendedModeLocalOrTauri')
        : probeRecommendedMode === 'start_local_editor_mcp'
          ? t('probeRecommendedModeStartLocalEditorMcp')
          : probeRecommendedMode === 'verify_local_network_and_editor'
            ? t('probeRecommendedModeVerifyLocalNetworkAndEditor')
            : null;

    const probeRecommendedActionLabel =
      probeRecommendedMode === 'local_or_tauri'
        ? t('probeRecommendedActionSwitchMode')
        : t('probeRecommendedActionRetryProbe');

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
            {connectGuide && (
              <div className="bg-muted rounded-md p-3">
                <p className="text-sm whitespace-pre-line">{connectGuide}</p>
              </div>
            )}

            {(probeStatus === 'unreachable' || probeStatus === 'cloud_not_supported') && probeError && (
              <div className="bg-destructive/10 border-destructive/20 rounded-md border p-3">
                <p className="text-destructive text-sm">{probeError}</p>
              </div>
            )}
            {(probeStatus === 'unreachable' || probeStatus === 'cloud_not_supported') &&
              probeRecommendedMode &&
              probeRecommendedMessage && (
                <div className="bg-muted rounded-md border p-3">
                  <p className="text-sm font-medium">{t('probeRecommendedActionTitle')}</p>
                  <p className="text-muted-foreground mt-1 text-sm">{probeRecommendedMessage}</p>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="mt-3"
                    disabled={probeStatus === 'probing' || connecting || oauthPolling}
                    onClick={handleProbeRecommendedAction}
                  >
                    {probeRecommendedActionLabel}
                  </Button>
                </div>
              )}

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
