'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Label } from '@/components/primitives/label';
import { QUICK_SETUP_PROVIDERS } from '@/lib/search/retrievalProviders';
import OptionSelect from '../OptionSelect';
import ApiKeyField from './ApiKeyField';
import type { QuickCredentials } from './retrievalSetup';

const PROVIDER_OPTIONS = QUICK_SETUP_PROVIDERS.map(({ id, name }) => ({ value: id, label: name }));

interface QuickSetupProps {
  credentials: QuickCredentials;
  onChange: (edit: Partial<QuickCredentials>) => void;
}

/** One provider and key for both retrieval models. */
const QuickSetup = memo<QuickSetupProps>(({ credentials, onChange }) => {
  const t = useTranslations('settings.retrieval');

  return (
    <div className="space-y-4 rounded-xl border border-border bg-muted/30 p-5">
      <div className="space-y-2">
        <Label className="text-sm font-medium">{t('provider')}</Label>
        <OptionSelect
          value={credentials.providerId}
          options={PROVIDER_OPTIONS}
          onChange={(providerId) => onChange({ providerId })}
          className="w-full"
        />
      </div>
      <ApiKeyField value={credentials.apiKey} onChange={(apiKey) => onChange({ apiKey })} />
    </div>
  );
});

QuickSetup.displayName = 'QuickSetup';

export default QuickSetup;
