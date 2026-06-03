'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import useConfigStore from '@/store/useConfigStore';
import MCPConfigForm from '../MCPConfigForm';
import SettingsSection from './SettingsSection';

const MCPSection = memo(() => {
  const t = useTranslations('settings');
  const { mcpConfigs, setMCPConfigs, initConfig } = useConfigStore();

  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    initConfig();
    setIsLoading(false);
  }, [initConfig]);

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
        <MCPConfigForm currentConfigs={mcpConfigs} onSave={setMCPConfigs} />
      </SettingsSection>
    </div>
  );
});

MCPSection.displayName = 'MCPSection';

export default MCPSection;
