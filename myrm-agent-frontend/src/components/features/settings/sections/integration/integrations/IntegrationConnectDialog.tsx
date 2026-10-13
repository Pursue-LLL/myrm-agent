'use client';

import { memo, useState, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { toast } from '@/hooks/shared/useToast';
import useConfigStore from '@/store/useConfigStore';
import { MCPScanAckDialog } from '@/components/features/settings/mcp/MCPScanAckDialog';
import type { MCPServiceConfig } from '@/store/config/types';
import { getDocsUrl, isSandbox } from '@/lib/deploy-mode';
import type { CatalogEntry, CatalogMcpDialogConfig } from './catalog-types';
import { shouldBlockLocalOnlyInSandbox } from './deploymentGuard';
import { AuthSection } from './connect-dialog/AuthSection';
import { ProbeDiagnostics } from './connect-dialog/ProbeDiagnostics';
import { resolveProbeUrl } from './connect-dialog/probe';
import { useCatalogOAuth } from './connect-dialog/useCatalogOAuth';
import { useCatalogSecurityGate } from './connect-dialog/useCatalogSecurityGate';
import { useConnectivityProbe } from './connect-dialog/useConnectivityProbe';

interface IntegrationConnectDialogProps {
  entry: CatalogEntry;
  locale: string;
  onClose: () => void;
  onConnected: () => void;
}

export const IntegrationConnectDialog = memo<IntegrationConnectDialogProps>(
  ({ entry, locale, onClose, onConnected }) => {
    const t = useTranslations('settings.integrationCatalog.connectDialog');
    const credentialFields = useMemo(() => entry.credentialFields ?? [], [entry.credentialFields]);
    const hasMultiFields = credentialFields.length > 0;

    const [credential, setCredential] = useState('');
    const [fieldValues, setFieldValues] = useState<Record<string, string>>(() =>
      Object.fromEntries(credentialFields.map((f) => [f.key, ''])),
    );
    const [connecting, setConnecting] = useState(false);
    const { mcpConfigs, setMCPConfigs } = useConfigStore();

    const helpText = locale === 'zh' && entry.helpTextZh ? entry.helpTextZh : entry.helpText;
    const connectGuide =
      locale === 'zh' && entry.postConnectGuideZh ? entry.postConnectGuideZh : entry.postConnectGuide;
    const mcpConfig = entry.mcpConfig as Record<string, unknown> | null;
    const probeUrl = resolveProbeUrl(mcpConfig);
    const deploymentScope = entry.deploymentScope ?? (mcpConfig?.deploymentScope as string | undefined) ?? null;
    const isLocalTauriOnlyEntry = deploymentScope === 'local_tauri_only';
    const isSandboxMode = isSandbox();

    const { probeStatus, probeError, probeRecommendedMode, runProbe, reportLocalOnlyBlocked } = useConnectivityProbe({
      probeUrl,
      isLocalTauriOnlyEntry,
      isSandboxMode,
    });
    const { pendingAck, runCatalogSecurityGate, confirmAcknowledgement, cancelAcknowledgement } =
      useCatalogSecurityGate({
        entryName: entry.name,
        catalogMcpConfig: mcpConfig,
        mcpConfigs,
        setMCPConfigs,
        onConnected,
      });
    const { oauthPolling, startOAuthConnect } = useCatalogOAuth({ entry, runCatalogSecurityGate });

    const handleFieldChange = useCallback((key: string, value: string) => {
      setFieldValues((prev) => ({ ...prev, [key]: value }));
    }, []);

    const handleConnect = useCallback(
      async (options?: { skipProbe?: boolean }) => {
        if (entry.authType === 'oauth2') {
          await startOAuthConnect();
          return;
        }

        if (entry.authType !== 'none') {
          if (hasMultiFields) {
            const empty = credentialFields.find((f) => !fieldValues[f.key]?.trim());
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
          reportLocalOnlyBlocked();
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

            const mcpCfg = entry.mcpConfig as unknown as CatalogMcpDialogConfig;

            let finalArgs = mcpCfg.args || [];
            const envMap: Record<string, string> = { ...mcpCfg.env };
            const headerMap: Record<string, string> = { ...mcpCfg.headers };

            if (hasMultiFields) {
              for (const field of credentialFields) {
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
              type: mcpCfg.type,
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
      },
      [
        entry,
        credential,
        fieldValues,
        hasMultiFields,
        isLocalTauriOnlyEntry,
        isSandboxMode,
        locale,
        mcpConfigs,
        t,
        probeUrl,
        runProbe,
        reportLocalOnlyBlocked,
        runCatalogSecurityGate,
        startOAuthConnect,
        credentialFields,
      ],
    );

    const handleProbeRecommendedAction = useCallback(async () => {
      if (probeRecommendedMode === 'local_or_tauri') {
        // noopener makes window.open return null by spec, so the result cannot tell a blocked popup from success.
        window.open(getDocsUrl('/getting-started/local-deployment'), '_blank', 'noopener,noreferrer');
        onClose();
        return;
      }
      const probeOk = await runProbe();
      if (!probeOk) {
        return;
      }
      await handleConnect({ skipProbe: true });
    }, [handleConnect, onClose, probeRecommendedMode, runProbe]);

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

              <ProbeDiagnostics
                probeStatus={probeStatus}
                probeError={probeError}
                probeRecommendedMode={probeRecommendedMode}
                actionDisabled={connecting || oauthPolling}
                onRecommendedAction={handleProbeRecommendedAction}
              />

              <AuthSection
                entry={entry}
                locale={locale}
                credentialFields={credentialFields}
                credential={credential}
                fieldValues={fieldValues}
                helpText={helpText}
                onCredentialChange={setCredential}
                onFieldChange={handleFieldChange}
              />
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={onClose}>
                {t('cancel')}
              </Button>
              <Button onClick={() => void handleConnect()} disabled={connecting || oauthPolling}>
                {oauthPolling
                  ? t('waitingAuth', { default: 'Waiting for authorization...' })
                  : connecting
                    ? t('connecting')
                    : t('connect')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <MCPScanAckDialog
          open={!!pendingAck}
          serverName={pendingAck?.config.name || ''}
          findings={pendingAck?.scanResult.findings ?? []}
          onConfirm={confirmAcknowledgement}
          onCancel={cancelAcknowledgement}
        />
      </>
    );
  },
);

IntegrationConnectDialog.displayName = 'IntegrationConnectDialog';
