'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import ThemePresetGrid from '@/components/features/theme/shared/ThemePresetGrid';
import useConfigStore from '@/store/useConfigStore';
import { OFFICIAL_DEFAULT_PROFILE_ID, getBuiltinProfile } from '@/theme-engine';
import {
  getOnboardingThemePresets,
  isOnboardingThemePresetId,
} from '@/components/features/onboarding/onboarding-theme-presets';

interface ThemeOnboardingStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

export default function ThemeOnboardingStep({ onComplete, onSkip }: ThemeOnboardingStepProps) {
  const t = useTranslations('boot.onboarding.themePick');
  const tAppearance = useTranslations('settings.appearancePanel');
  const updatePersonalSettings = useConfigStore((state) => state.updatePersonalSettings);

  const presets = getOnboardingThemePresets();
  const [selectedId, setSelectedId] = useState<string>(OFFICIAL_DEFAULT_PROFILE_ID);
  const [busy, setBusy] = useState(false);

  const handleContinue = useCallback(async () => {
    if (!isOnboardingThemePresetId(selectedId)) {
      onComplete();
      return;
    }
    const profile = getBuiltinProfile(selectedId);
    if (!profile) {
      onComplete();
      return;
    }
    setBusy(true);
    try {
      await updatePersonalSettings({
        activeThemeProfileId: profile.id,
        themeFontOverride: profile.fontId,
      });
      onComplete();
    } finally {
      setBusy(false);
    }
  }, [onComplete, selectedId, updatePersonalSettings]);

  return (
    <div className="space-y-6">
      <ThemePresetGrid
        profiles={presets}
        activeProfileId={selectedId}
        labelForProfile={(profile) =>
          tAppearance(`presets.${profile.id}` as 'presets.official-default')
        }
        onSelect={setSelectedId}
      />
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-center sm:gap-3">
        <Button type="button" variant="ghost" disabled={busy} onClick={onSkip}>
          {t('skipButton')}
        </Button>
        <Button type="button" disabled={busy} onClick={() => void handleContinue()} className="inline-flex items-center gap-2">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          {t('continueButton')}
        </Button>
      </div>
    </div>
  );
}
