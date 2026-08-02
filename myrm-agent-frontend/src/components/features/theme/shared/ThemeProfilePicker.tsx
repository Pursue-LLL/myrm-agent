'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import ThemePresetGrid from '@/components/features/theme/shared/ThemePresetGrid';
import { listManagedProfiles } from '@/components/features/theme-studio/studio-profile';
import {
  BUILTIN_THEME_PROFILES,
  EMPTY_THEME_PROFILES,
  type ThemeProfileRecipe,
} from '@/theme-engine';

interface ThemeProfilePickerProps {
  themeProfiles?: ThemeProfileRecipe[];
  activeProfileId: string;
  onSelect: (profileId: string) => void;
}

const ThemeProfilePicker = ({
  themeProfiles = EMPTY_THEME_PROFILES,
  activeProfileId,
  onSelect,
}: ThemeProfilePickerProps) => {
  const tAppearance = useTranslations('settings.appearancePanel');
  const tStudio = useTranslations('settings.themeStudio.profilePicker');

  const managedProfiles = useMemo(() => listManagedProfiles(themeProfiles), [themeProfiles]);

  const labelForProfile = (profile: ThemeProfileRecipe): string => {
    if (profile.builtin) {
      return tAppearance(`presets.${profile.id}` as 'presets.official-default');
    }
    return profile.name.trim() || profile.id;
  };

  return (
    <div className="space-y-3">
      <ThemePresetGrid
        profiles={BUILTIN_THEME_PROFILES}
        activeProfileId={activeProfileId}
        labelForProfile={labelForProfile}
        onSelect={onSelect}
      />
      {managedProfiles.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">{tStudio('savedTitle')}</p>
          <ThemePresetGrid
            profiles={managedProfiles}
            activeProfileId={activeProfileId}
            labelForProfile={labelForProfile}
            onSelect={onSelect}
          />
        </div>
      ) : null}
    </div>
  );
};

export default ThemeProfilePicker;
