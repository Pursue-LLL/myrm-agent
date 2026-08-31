'use client';

/**
 * [INPUT]
 * - @/store/useProviderStore, useConfigStore (POS: 前端配置与 Provider 状态)
 * - @/lib/deploy-mode::isSandbox, isTauriRuntime, @/lib/api::apiRequest
 * - @/services/connect::listConnectorStatus, @/services/integrations/oauthCredentials::listOAuthCredentials
 * - @/services/channels/manage::listChannelStatuses
 * - ./providerDataUsageCatalog, ./DataFlowYourRightsStrip
 *
 * [OUTPUT]
 * - DataFlowDisclosurePanel
 *
 * [POS]
 * Settings Security 区数据流向披露 SSOT：本地域 / 控制平面 / 第三方 egress（含 Tauri Channel）/ 数据权利。
 */

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import {
  IconShieldCheck,
  IconDatabase,
  IconGlobe,
  IconLock,
  IconServer,
  IconArrowRight,
  IconShield,
} from '@/components/features/icons/PremiumIcons';
import { ExternalLink } from 'lucide-react';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import { getProviderCategory } from '@/store/config/providerTypes';
import { isSandbox, isTauriRuntime } from '@/lib/deploy-mode';
import { apiRequest } from '@/lib/api';
import { listConnectorStatus, type ConnectorStatus } from '@/services/connect';
import {
  listOAuthCredentials,
  type OAuthCredentialItem,
} from '@/services/integrations/oauthCredentials';
import { listChannelStatuses, type ChannelStatus } from '@/services/channels/manage';
import { resolveProviderDataUsage } from './providerDataUsageCatalog';
import {
  buildChannelEgressSnapshot,
  buildConnectorEgressSnapshot,
  buildOAuthEgressSnapshot,
  DataFlowYourRightsStrip,
  type ComplianceEgressSnapshot,
} from './DataFlowYourRightsStrip';
import SettingsSection from '../SettingsSection';

export interface DataFlowDisclosurePanelProps {
  onNavigateToProviders?: () => void;
  onNavigateToMcp?: () => void;
}

function isHostedDeployMode(frontendSandbox: boolean, backendDeployMode: string | null): boolean {
  return frontendSandbox || backendDeployMode === 'sandbox';
}

function formatOAuthLabel(issuer: string): string {
  return issuer
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export const DataFlowDisclosurePanel = memo(
  ({ onNavigateToProviders, onNavigateToMcp }: DataFlowDisclosurePanelProps) => {
    const t = useTranslations('settings.securityPolicy.dataFlow');

    const providers = useProviderStore((state) => state.providers);
    const mcpConfigs = useConfigStore((state) => state.mcpConfigs);
    const privacyEnabled = useConfigStore((state) => state.privacyEnabled);
    const privacyRouting = useConfigStore((state) => state.privacyRouting);

    const [backendDeployMode, setBackendDeployMode] = useState<string | null>(null);
    const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
    const [oauthIntegrations, setOauthIntegrations] = useState<OAuthCredentialItem[]>([]);
    const [channels, setChannels] = useState<ChannelStatus[]>([]);
    const [integrationsLoaded, setIntegrationsLoaded] = useState(false);

    useEffect(() => {
      let cancelled = false;
      void apiRequest<{ deploy_mode: string }>('/health/info')
        .then((info) => {
          if (!cancelled) {
            setBackendDeployMode(info.deploy_mode);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setBackendDeployMode(null);
          }
        });
      return () => {
        cancelled = true;
      };
    }, []);

    const fetchIntegrations = useCallback(async () => {
      const channelFetch = isTauriRuntime()
        ? listChannelStatuses().catch(() => [] as ChannelStatus[])
        : Promise.resolve([] as ChannelStatus[]);
      const [connectorResult, oauthResult, channelResult] = await Promise.allSettled([
        listConnectorStatus(),
        listOAuthCredentials(),
        channelFetch,
      ]);
      setConnectors(connectorResult.status === 'fulfilled' ? connectorResult.value : []);
      setOauthIntegrations(oauthResult.status === 'fulfilled' ? oauthResult.value : []);
      setChannels(channelResult.status === 'fulfilled' ? channelResult.value : []);
      setIntegrationsLoaded(true);
    }, []);

    useEffect(() => {
      void fetchIntegrations();
    }, [fetchIntegrations]);

    useEffect(() => {
      const refreshIntegrations = () => {
        void fetchIntegrations();
      };

      window.addEventListener('channel-status-change', refreshIntegrations);
      window.addEventListener('channel-credentials-saved', refreshIntegrations);
      return () => {
        window.removeEventListener('channel-status-change', refreshIntegrations);
        window.removeEventListener('channel-credentials-saved', refreshIntegrations);
      };
    }, [fetchIntegrations]);

    const activeProviders = useMemo(() => providers.filter((p) => p.isEnabled), [providers]);
    const activeMcpConfigs = useMemo(() => mcpConfigs.filter((m) => m.enabled), [mcpConfigs]);
    const activeConnectors = useMemo(
      () => connectors.filter((c) => c.status === 'ready' && c.connected_at),
      [connectors],
    );
    const activeOAuthIntegrations = useMemo(
      () => oauthIntegrations.filter((item) => item.connected),
      [oauthIntegrations],
    );
    const activeChannels = useMemo(
      () => channels.filter((channel) => channel.connected),
      [channels],
    );

    const egressCount =
      activeProviders.length +
      activeMcpConfigs.length +
      activeConnectors.length +
      activeOAuthIntegrations.length +
      activeChannels.length;
    const hasSyncEgress = activeProviders.length > 0 || activeMcpConfigs.length > 0;
    const hasAsyncEgress =
      activeConnectors.length > 0 || activeOAuthIntegrations.length > 0 || activeChannels.length > 0;
    const hasEgress = hasSyncEgress || hasAsyncEgress;
    const hostedControlPlane = isHostedDeployMode(isSandbox(), backendDeployMode);

    const hasCloudEgress = useMemo(
      () =>
        activeProviders.some((p) => getProviderCategory(p.id) !== 'local') ||
        activeOAuthIntegrations.length > 0,
      [activeOAuthIntegrations.length, activeProviders],
    );

    const showCrossBorderHint =
      privacyEnabled && Boolean(privacyRouting?.localModel?.trim()) && hasCloudEgress;

    const egressSnapshot = useMemo((): ComplianceEgressSnapshot => {
      return {
        providers: activeProviders.map((p) => ({
          id: p.id,
          name: p.name,
          endpoint: p.apiHost || p.apiUrl || t('fallbackCloudEndpoint'),
        })),
        mcp: activeMcpConfigs.map((m) => ({
          name: m.name,
          transport: m.type || 'stdio',
          endpoint: m.url || m.command || t('fallbackLocalStdio'),
        })),
        connectors: buildConnectorEgressSnapshot(connectors),
        oauthIntegrations: buildOAuthEgressSnapshot(oauthIntegrations),
        channels: buildChannelEgressSnapshot(channels),
      };
    }, [activeMcpConfigs, activeProviders, channels, connectors, oauthIntegrations, t]);

    const renderEgressBody = () => {
      if (!integrationsLoaded && !hasSyncEgress) {
        return (
          <div className="p-4 rounded-lg border border-dashed border-border/60 text-center text-xs text-muted-foreground">
            {t('egressLoading')}
          </div>
        );
      }

      if (!hasEgress && integrationsLoaded) {
        return (
          <div className="p-4 rounded-lg border border-dashed border-border/60 text-center text-xs text-muted-foreground">
            {t('noEgress')}
          </div>
        );
      }

      return (
        <div className="space-y-2 pt-1">
          {!integrationsLoaded && hasSyncEgress && (
            <p className="text-[11px] text-muted-foreground px-1">{t('integrationsLoading')}</p>
          )}

          {activeProviders.map((provider) => {
            const category = getProviderCategory(provider.id);
            const isLocal = category === 'local';
            const endpoint = provider.apiHost || provider.apiUrl || t('fallbackCloudEndpoint');
            const dataUsage = resolveProviderDataUsage(provider.id, isLocal);

            return (
              <div
                key={provider.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg border border-border/40 bg-background/50 gap-2.5"
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-foreground">{provider.name}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-primary/10 text-primary">
                      {t('llmCategory')}
                    </span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                        isLocal
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                          : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                      }`}
                    >
                      {isLocal ? t('badgeLocalHost') : t('badgeCloudApi')}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 truncate">
                    <span className="font-mono text-[10px] opacity-80">{endpoint}</span>
                    <span>•</span>
                    <span>{t('dataScopePrompt')}</span>
                  </div>
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1 flex-wrap">
                    <span>{t(`dataUsage.${dataUsage.policyKey}`)}</span>
                    {dataUsage.docUrl && (
                      <a
                        href={dataUsage.docUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-0.5 text-primary hover:underline"
                      >
                        {t('dataUsagePolicyLink')}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>

                {onNavigateToProviders ? (
                  <button
                    type="button"
                    onClick={onNavigateToProviders}
                    className="self-end sm:self-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {t('actionManage')}
                    <IconArrowRight className="h-3 w-3" />
                  </button>
                ) : (
                  <Link
                    href="/settings/models"
                    className="self-end sm:self-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {t('actionManage')}
                    <IconArrowRight className="h-3 w-3" />
                  </Link>
                )}
              </div>
            );
          })}

          {activeMcpConfigs.map((mcp) => (
            <div
              key={mcp.name}
              className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg border border-border/40 bg-background/50 gap-2.5"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-foreground">{mcp.name}</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-500/10 text-purple-600 dark:text-purple-400">
                    {t('mcpCategory')}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-secondary text-secondary-foreground uppercase">
                    {mcp.type || 'stdio'}
                  </span>
                </div>
                <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 truncate">
                  <span className="font-mono text-[10px] opacity-80">
                    {mcp.url || mcp.command || t('fallbackLocalStdio')}
                  </span>
                  <span>•</span>
                  <span>{t('dataScopeToolArgs')}</span>
                </div>
              </div>

              {onNavigateToMcp ? (
                <button
                  type="button"
                  onClick={onNavigateToMcp}
                  className="self-end sm:self-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {t('actionManage')}
                  <IconArrowRight className="h-3 w-3" />
                </button>
              ) : (
                <Link
                  href="/settings/mcp"
                  className="self-end sm:self-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {t('actionManage')}
                  <IconArrowRight className="h-3 w-3" />
                </Link>
              )}
            </div>
          ))}

          {integrationsLoaded &&
            activeOAuthIntegrations.map((integration) => (
              <div
                key={integration.issuer}
                className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg border border-border/40 bg-background/50 gap-2.5"
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-foreground">
                      {formatOAuthLabel(integration.issuer)}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                      {t('integrationOAuthCategory')}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">{t('dataScopeIntegration')}</div>
                </div>

                <Link
                  href="/settings/integrationCatalog"
                  className="self-end sm:self-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {t('actionManage')}
                  <IconArrowRight className="h-3 w-3" />
                </Link>
              </div>
            ))}

          {integrationsLoaded &&
            activeConnectors.map((connector) => (
              <div
                key={connector.profile_id}
                className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg border border-border/40 bg-background/50 gap-2.5"
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-foreground">{connector.label}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-cyan-500/10 text-cyan-600 dark:text-cyan-400">
                      {t('agentConnectorCategory')}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">{t('dataScopeConnector')}</div>
                </div>

                <Link
                  href="/settings/connect"
                  className="self-end sm:self-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {t('actionManage')}
                  <IconArrowRight className="h-3 w-3" />
                </Link>
              </div>
            ))}

          {integrationsLoaded &&
            activeChannels.map((channel) => (
              <div
                key={channel.instanceId}
                className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg border border-border/40 bg-background/50 gap-2.5"
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-foreground">
                      {channel.displayName || channel.name}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-500/10 text-rose-600 dark:text-rose-400">
                      {t('channelCategory')}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-secondary text-secondary-foreground uppercase">
                      {channel.channelType}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">{t('dataScopeChannel')}</div>
                </div>

                <Link
                  href="/settings/channels"
                  className="self-end sm:self-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {t('actionManage')}
                  <IconArrowRight className="h-3 w-3" />
                </Link>
              </div>
            ))}
        </div>
      );
    };

    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="space-y-6">
          {/* 1. Local Private Domain */}
          <div className="rounded-xl border border-border/60 bg-muted/20 p-4.5 space-y-3.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
                  <IconShieldCheck className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-foreground">{t('localDomain')}</h4>
                  <p className="text-xs text-muted-foreground">{t('localDomainDesc')}</p>
                </div>
              </div>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                {t('badgeLocalOnly')}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
              <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-border/40 bg-background/50">
                <IconDatabase className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-foreground">{t('localChatHistory')}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{t('localChatHistoryDesc')}</div>
                </div>
              </div>

              <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-border/40 bg-background/50">
                <IconServer className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-foreground">{t('localMemory')}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{t('localMemoryDesc')}</div>
                </div>
              </div>

              <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-border/40 bg-background/50">
                <IconShield className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-foreground">{t('localWorkspace')}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{t('localWorkspaceDesc')}</div>
                </div>
              </div>

              <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-border/40 bg-background/50">
                <IconLock className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-foreground">{t('localCredentials')}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{t('localCredentialsDesc')}</div>
                </div>
              </div>
            </div>
          </div>

          {/* 2. Control Plane & Telemetry Domain */}
          <div className="rounded-xl border border-border/60 bg-muted/20 p-4.5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/10 text-blue-500">
                  <IconServer className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-foreground">{t('controlPlaneDomain')}</h4>
                  <p className="text-xs text-muted-foreground">{t('controlPlaneDesc')}</p>
                </div>
              </div>
            </div>

            <div className="p-3 rounded-lg border border-border/40 bg-background/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <div className="text-xs font-medium text-foreground">
                  {hostedControlPlane ? t('controlPlaneHosted') : t('controlPlaneStandalone')}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {hostedControlPlane ? t('controlPlaneHostedDesc') : t('controlPlaneStandaloneDesc')}
                </div>
              </div>
              <span
                className={`self-start sm:self-auto px-2 py-0.5 rounded text-[11px] font-medium ${
                  hostedControlPlane
                    ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                    : 'bg-secondary text-secondary-foreground'
                }`}
              >
                {hostedControlPlane ? t('badgeHosted') : t('badgeLocalOnly')}
              </span>
            </div>
          </div>

          {/* 3. Third-Party Outbound Egress */}
          <div className="rounded-xl border border-border/60 bg-muted/20 p-4.5 space-y-3.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/10 text-amber-500">
                  <IconGlobe className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-foreground">{t('egressDomain')}</h4>
                  <p className="text-xs text-muted-foreground">{t('egressDesc')}</p>
                </div>
              </div>
              {integrationsLoaded && (
                <span className="text-xs font-medium text-muted-foreground">
                  {t('badgeActiveCount', { count: egressCount })}
                </span>
              )}
            </div>

            {showCrossBorderHint && (
              <div className="p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 text-[11px] text-muted-foreground">
                {t('crossBorderRoutingHint')}{' '}
                <a href="#security-privacy-routing" className="text-primary hover:underline font-medium">
                  {t('crossBorderRoutingLink')}
                </a>
              </div>
            )}

            {renderEgressBody()}
          </div>

          <DataFlowYourRightsStrip egressSnapshot={egressSnapshot} />
        </div>
      </SettingsSection>
    );
  },
);

DataFlowDisclosurePanel.displayName = 'DataFlowDisclosurePanel';
