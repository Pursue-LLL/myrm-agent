'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import ConfigImportExport from '../ConfigImportExport';
import SettingsSection from './SettingsSection';

const ImportExportSection = memo(() => {
  const t = useTranslations('settings');

  return (
    <div className="space-y-6">
      <SettingsSection title={t('configImportExport')}>
        <ConfigImportExport />
      </SettingsSection>
    </div>
  );
});

ImportExportSection.displayName = 'ImportExportSection';

export default ImportExportSection;
