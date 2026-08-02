'use client';

import { cn } from '@/lib/utils/classnameUtils';
import type { ThemeProfileRecipe } from '@/theme-engine';

interface ThemePresetGridProps {
  profiles: ThemeProfileRecipe[];
  activeProfileId: string;
  labelForProfile: (profile: ThemeProfileRecipe) => string;
  onSelect: (profileId: string) => void;
}

const ThemePresetGrid = ({
  profiles,
  activeProfileId,
  labelForProfile,
  onSelect,
}: ThemePresetGridProps) => (
  <div className="flex flex-wrap gap-2">
    {profiles.map((profile) => (
      <button
        key={profile.id}
        type="button"
        onClick={() => onSelect(profile.id)}
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-all',
          activeProfileId === profile.id
            ? 'border-primary bg-primary/10 text-foreground ring-1 ring-accent-warm/35'
            : 'border-border bg-secondary/40 text-muted-foreground hover:text-foreground',
        )}
      >
        <PresetSwatch profile={profile} />
        {labelForProfile(profile)}
      </button>
    ))}
  </div>
);

function PresetSwatch({ profile }: { profile: ThemeProfileRecipe }) {
  const swatch = profile.palette.primaryLight;
  const warm = profile.palette.accentWarmLight;

  return (
    <span
      className={cn(
        'w-4 h-4 rounded-full shrink-0 ring-1 ring-black/10 dark:ring-white/10 overflow-hidden',
        profile.palette.dualAccent ? 'flex' : 'block',
      )}
      aria-hidden
    >
      {profile.palette.dualAccent && warm ? (
        <>
          <span className="w-1/2 h-full" style={{ backgroundColor: swatch }} />
          <span className="w-1/2 h-full" style={{ backgroundColor: warm }} />
        </>
      ) : (
        <span className="block w-full h-full" style={{ backgroundColor: swatch }} />
      )}
    </span>
  );
}

export default ThemePresetGrid;
