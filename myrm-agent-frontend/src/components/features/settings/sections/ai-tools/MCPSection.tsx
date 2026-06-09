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
  const { mcpConfigs, setMCPConfigs, addMCPConfig, initConfig } = useConfigStore();
  const { toast } = useToast();

  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<MCPTab>('installed');
  const [installTarget, setInstallTarget] = useState<string | null>(null);

  useEffect(() => {
    initConfig();
    setIsLoading(false);
  }, [initConfig]);

  const installedNames = useMemo(
    () => new Set(mcpConfigs.map((c) => c.name)),
    [mcpConfigs],
  );

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
      if (batchGate.scanResults[0]) {
        const { buildLastScanSummary } = await import('@/hooks/useMcpSecurityGate');
        config.lastScanSummary = buildLastScanSummary(batchGate.scanResults[0]);
      }
      addMCPConfig(config);
      toast({
        title: t('mcpRegistryInstallSuccess'),
        description: t('mcpRegistryInstallSuccessDesc', { name: config.name }),
      });
      setInstallTarget(null);
      setActiveTab('installed');
    },
    [addMCPConfig, toast, t],
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
            {t('mcpTabInstalled')} ({mcpConfigs.length})
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
          <MCPConfigForm currentConfigs={mcpConfigs} onSave={setMCPConfigs} />
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
