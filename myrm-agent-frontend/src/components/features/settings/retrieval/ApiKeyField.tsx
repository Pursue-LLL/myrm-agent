'use client';

import { memo, useId, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';

interface ApiKeyFieldProps {
  value: string;
  onChange: (value: string) => void;
}

/** Masked API key input with a reveal toggle, shared by the quick setup and the per-model selectors. */
const ApiKeyField = memo<ApiKeyFieldProps>(({ value, onChange }) => {
  const t = useTranslations('settings.retrieval');
  const inputId = useId();
  const [visible, setVisible] = useState(false);

  return (
    <div className="space-y-2">
      <Label htmlFor={inputId} className="text-sm font-medium">
        {t('apiKey')}
      </Label>
      <div className="relative">
        <Input
          id={inputId}
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={t('apiKeyPlaceholder')}
          autoComplete="off"
          className="pr-10"
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={visible ? t('hideApiKey') : t('showApiKey')}
          className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? (
            <IconEyeOff className="h-4 w-4 text-muted-foreground" />
          ) : (
            <IconEye className="h-4 w-4 text-muted-foreground" />
          )}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t('apiKeyHint')}</p>
    </div>
  );
});

ApiKeyField.displayName = 'ApiKeyField';

export default ApiKeyField;
