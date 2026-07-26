'use client';

import { useState, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import useProviderStore from '@/store/useProviderStore';
import { getConfigSyncManager } from '@/services/config';
import type { SecurityConfigValue } from '@/services/config/types';
import type { SingleModelSelection } from '@/store/config/providerTypes';
import EnabledModelSelect from '@/components/features/settings/default-model/EnabledModelSelect';
import { IconShieldCheck } from '@/components/features/icons/PremiumIcons';
import { DEFAULT_CONFIG } from '@/components/features/settings/sections/system/securityPolicyUtils';

const CHEAP_MODEL_KEYWORDS = ['mini', 'flash', 'haiku', 'nano', 'lite', 'small'] as const;

function pickCheapestModel(
  enabledModels: { providerId: string; model: string }[],
): SingleModelSelection | null {
  if (enabledModels.length === 0) return null;
  const cheap = enabledModels.find((m) =>
    CHEAP_MODEL_KEYWORDS.some((k) => m.model.toLowerCase().includes(k)),
  );
  return cheap
    ? { providerId: cheap.providerId, model: cheap.model }
    : { providerId: enabledModels[0].providerId, model: enabledModels[0].model };
}

interface SmartGuardStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

export default function SmartGuardStep({ onComplete, onSkip }: SmartGuardStepProps) {
  const t = useTranslations('boot.onboarding.smartGuard');

  const providers = useProviderStore((s) => s.providers);
  const getEnabledModels = useProviderStore((s) => s.getEnabledModels);
  const enabledModels = useMemo(() => getEnabledModels(), [getEnabledModels]);

  const preselected = useMemo(() => pickCheapestModel(enabledModels), [enabledModels]);
  const [enabled, setEnabled] = useState(true);
  const [selectedModel, setSelectedModel] = useState<SingleModelSelection | null>(preselected);

  const handleEnable = useCallback(() => {
    if (!selectedModel) return;
    const syncManager = getConfigSyncManager();
    const current = syncManager.get('securityConfig') as SecurityConfigValue | null;
    syncManager.set('securityConfig', {
      ...(current ?? DEFAULT_CONFIG),
      autoReviewEnabled: true,
      autoReviewModel: `${selectedModel.providerId}/${selectedModel.model}`,
    });
    onComplete();
  }, [selectedModel, onComplete]);

  const handleToggle = useCallback((checked: boolean) => {
    setEnabled(checked);
  }, []);

  const handleModelChange = useCallback((selection: SingleModelSelection | null) => {
    setSelectedModel(selection);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4 p-4 rounded-lg border border-border bg-muted/30">
        <div className="mt-0.5 p-2 rounded-full bg-primary/10 text-primary shrink-0">
          <IconShieldCheck className="h-5 w-5" />
        </div>
        <div className="flex-1 space-y-1">
          <p className="text-sm font-medium">{t('title')}</p>
          <p className="text-sm text-muted-foreground">{t('description')}</p>
        </div>
        <Switch checked={enabled} onCheckedChange={handleToggle} />
      </div>

      {enabled && (
        <div className="space-y-3 pl-2">
          <EnabledModelSelect
            label={t('modelLabel')}
            value={selectedModel}
            onChange={handleModelChange}
            enabledModels={enabledModels}
            providers={providers}
            placeholder={t('modelPlaceholder')}
          />
          <p className="text-xs text-muted-foreground">{t('costHint')}</p>
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <Button variant="ghost" onClick={onSkip}>
          {t('skip')}
        </Button>
        <Button
          onClick={enabled ? handleEnable : onSkip}
          disabled={enabled && !selectedModel}
        >
          {enabled ? t('enable') : t('skip')}
        </Button>
      </div>
    </div>
  );
}
