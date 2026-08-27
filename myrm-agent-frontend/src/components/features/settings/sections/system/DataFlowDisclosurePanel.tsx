'use client';

import { memo, useMemo } from 'react';
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
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import { getProviderCategory } from '@/store/config/providerTypes';
import SettingsSection from '../SettingsSection';

export interface DataFlowDisclosurePanelProps {
  onNavigateToProviders?: () => void;
  onNavigateToMcp?: () => void;
}

export const DataFlowDisclosurePanel = memo(
  ({ onNavigateToProviders, onNavigateToMcp }: DataFlowDisclosurePanelProps) => {
    const t = useTranslations('settings.securityPolicy.dataFlow');

    const providers = useProviderStore((state) => state.providers);
    const mcpConfigs = useConfigStore((state) => state.mcpConfigs);

    // Active external LLM providers
    const activeProviders = useMemo(() => {
      return providers.filter((p) => p.isEnabled);
    }, [providers]);

    // Active external MCP servers
    const activeMcpConfigs = useMemo(() => {
      return mcpConfigs.filter((m) => m.enabled);
    }, [mcpConfigs]);

    const hasEgress = activeProviders.length > 0 || activeMcpConfigs.length > 0;

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
                <div className="text-xs font-medium text-foreground">{t('controlPlaneStandalone')}</div>
                <div className="text-[11px] text-muted-foreground">{t('controlPlaneStandaloneDesc')}</div>
              </div>
              <span className="self-start sm:self-auto px-2 py-0.5 rounded text-[11px] font-medium bg-secondary text-secondary-foreground">
                {t('badgeLocalOnly')}
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
              <span className="text-xs font-medium text-muted-foreground">
                {activeProviders.length + activeMcpConfigs.length} Active
              </span>
            </div>

            {!hasEgress ? (
              <div className="p-4 rounded-lg border border-dashed border-border/60 text-center text-xs text-muted-foreground">
                {t('noEgress')}
              </div>
            ) : (
              <div className="space-y-2 pt-1">
                {/* Providers */}
                {activeProviders.map((provider) => {
                  const category = getProviderCategory(provider.id);
                  const isLocal = category === 'local';
                  const endpoint = provider.apiHost || provider.apiUrl || 'Cloud Endpoint';

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
                      </div>

                      {onNavigateToProviders && (
                        <button
                          type="button"
                          onClick={onNavigateToProviders}
                          className="self-end sm:self-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                        >
                          {t('actionManage')}
                          <IconArrowRight className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  );
                })}

                {/* MCP Servers */}
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
                          {mcp.url || mcp.command || 'Local STDIO'}
                        </span>
                        <span>•</span>
                        <span>{t('dataScopeToolArgs')}</span>
                      </div>
                    </div>

                    {onNavigateToMcp && (
                      <button
                        type="button"
                        onClick={onNavigateToMcp}
                        className="self-end sm:self-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {t('actionManage')}
                        <IconArrowRight className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </SettingsSection>
    );
  },
);

DataFlowDisclosurePanel.displayName = 'DataFlowDisclosurePanel';
