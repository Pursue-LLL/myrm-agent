'use client';

import { memo, useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import useConfigStore from '@/store/useConfigStore';
import MCPConfigForm from '../../MCPConfigForm';
import { MCPRegistryBrowser } from '../../mcp/MCPRegistryBrowser';
import { MCPInstallWizard } from '../../mcp/MCPInstallWizard';
import SettingsSection from '../SettingsSection';
import { useToast } from '@/hooks/useToast';
import { gateMcpConfigBatch } from '@/hooks/useMcpSecurityGate';
import type { MCPServiceConfig } from '@/store/config/types';

type MCPTab = 'installed' | 'registry';

const MCPSection = memo(() => {
  const t = useTranslations('settings');
  const { mcpConfigs, orgMcpConfigs, setMCPConfigs, addMCPConfig, initConfig } = useConfigStore();
  const { toast } = useToast();

  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<MCPTab>('installed');
  const [installTarget, setInstallTarget] = useState<string | null>(null);

  useEffect(() => {
    initConfig();
    setIsLoading(false);
  }, [initConfig]);

  const installedNames = useMemo(() => {
    const names = new Set<string>();
    for (const c of mcpConfigs) {
      names.add(c.name);
      const qn = (c.extra_params as Record<string, unknown> | undefined)?.registryQualifiedName;
      if (typeof qn === 'string') names.add(qn);
    }
    return names;
  }, [mcpConfigs]);

  const handleSelectInstall = useCallback((qualifiedName: string) => {
    setInstallTarget(qualifiedName);
  }, []);

  const handleInstallConfig = useCallback(
    async (config: MCPServiceConfig) => {
      const batchGate = await gateMcpConfigBatch([config]);
      if (batchGate.blocked) {
        toast({
          title: t('mcpScanBlocked'),
          description: t('mcpRegistryInstallBlocked'),
          variant: 'destructive',
        });
        return;
      }
      let finalConfig = { ...config };
      if (batchGate.scanResults[0]) {
        const { buildLastScanSummary } = await import('@/hooks/useMcpSecurityGate');
        finalConfig = { ...finalConfig, lastScanSummary: buildLastScanSummary(batchGate.scanResults[0]) };
      }
      const existingNames = new Set(mcpConfigs.map((c) => c.name));
      if (existingNames.has(finalConfig.name)) {
        let suffix = 2;
        while (existingNames.has(`${finalConfig.name}-${suffix}`)) suffix++;
        finalConfig = { ...finalConfig, name: `${finalConfig.name}-${suffix}` };
      }
      addMCPConfig(finalConfig);
      toast({
        title: t('mcpRegistryInstallSuccess'),
        description: t('mcpRegistryInstallSuccessDesc', { name: finalConfig.name }),
      });
      setInstallTarget(null);
      setActiveTab('installed');
    },
    [addMCPConfig, mcpConfigs, toast, t],
  );

  const handleCancelInstall = useCallback(() => {
    setInstallTarget(null);
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-5">
        <div className="space-y-1.5">
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-4 w-64" />
        </div>
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SettingsSection title={t('menu.mcp')}>
        <div className="flex items-center gap-1 mb-4 bg-secondary rounded-lg p-1">
          <button
            onClick={() => { setActiveTab('installed'); setInstallTarget(null); }}
            className={`flex-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'installed'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t('mcpTabInstalled')} ({mcpConfigs.length + orgMcpConfigs.length})
          </button>
          <button
            onClick={() => { setActiveTab('registry'); setInstallTarget(null); }}
            className={`flex-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'registry'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t('mcpTabRegistry')}
          </button>
        </div>

        {activeTab === 'installed' && (
          <>
            {orgMcpConfigs.length > 0 && (
              <div className="mb-4 space-y-2">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {t('mcpOrgManaged')}
                </p>
                {orgMcpConfigs.map((cfg) => (
                  <div
                    key={cfg.name}
                    className="flex items-center justify-between rounded-lg border border-border/50 bg-muted/30 px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="h-2 w-2 rounded-full bg-emerald-500" />
                      <div>
                        <p className="text-sm font-medium">{cfg.name}</p>
                        {cfg.description && (
                          <p className="text-xs text-muted-foreground">{cfg.description}</p>
                        )}
                      </div>
                    </div>
                    <span className="text-xs font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded">
                      {t('mcpOrgBadge')}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <MCPConfigForm currentConfigs={mcpConfigs} onSave={setMCPConfigs} />
          </>
        )}

        {activeTab === 'registry' && !installTarget && (
          <MCPRegistryBrowser
            installedNames={installedNames}
            onSelectInstall={handleSelectInstall}
          />
        )}

        {activeTab === 'registry' && installTarget && (
          <MCPInstallWizard
            qualifiedName={installTarget}
            onInstall={handleInstallConfig}
            onCancel={handleCancelInstall}
          />
        )}
      </SettingsSection>
    </div>
  );
});

MCPSection.displayName = 'MCPSection';

export default MCPSection;
