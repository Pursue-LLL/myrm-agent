'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import SettingsSection from './SettingsSection';

const LocalFileSearchSection = memo(() => {
  const t = useTranslations('localFileSearch');

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      <div className="rounded-xl border border-border/40 bg-card/30 p-6 text-center">
        <p className="text-sm text-muted-foreground">
          {t('noDirectories')}
        </p>
      </div>
    </SettingsSection>
  );
});

LocalFileSearchSection.displayName = 'LocalFileSearchSection';

export default LocalFileSearchSection;
