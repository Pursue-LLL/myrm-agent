'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import ConfigImportExport from '../../ConfigImportExport';
import SettingsSection from '../SettingsSection';
import DatasetExportCard from './DatasetExportCard';
import { StorageGovernanceCard } from './StorageGovernanceCard';
import SupportDebugBundleCard from './SupportDebugBundleCard';

const ImportExportSection = memo(() => {
  const t = useTranslations('settings');

  return (
    <div className="space-y-6">
      <SettingsSection title={t('configImportExport')}>
        <ConfigImportExport />
      </SettingsSection>
      <StorageGovernanceCard />
      <SupportDebugBundleCard />
      <DatasetExportCard />
    </div>
  );
});

ImportExportSection.displayName = 'ImportExportSection';

export default ImportExportSection;
