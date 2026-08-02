'use client';

import { useTranslations } from 'next-intl';
import { Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { listManagedProfiles } from '@/components/features/theme-studio/studio-profile';
import type { ThemeProfileRecipe } from '@/theme-engine';

interface ProfileLibraryPanelProps {
  profiles: ThemeProfileRecipe[];
  activeProfileId: string | undefined;
  onEdit: (profile: ThemeProfileRecipe) => void;
  onApply: (profile: ThemeProfileRecipe) => void;
  onDelete: (profileId: string) => void;
}

const ProfileLibraryPanel = ({
  profiles,
  activeProfileId,
  onEdit,
  onApply,
  onDelete,
}: ProfileLibraryPanelProps) => {
  const t = useTranslations('settings.themeStudio.library');
  const managed = listManagedProfiles(profiles);

  if (managed.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('empty')}</p>;
  }

  return (
    <ul className="space-y-2">
      {managed.map((profile) => (
        <li
          key={profile.id}
          className={cn(
            'flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2',
            activeProfileId === profile.id ? 'border-primary bg-primary/5' : 'border-border',
          )}
        >
          <button
            type="button"
            className="min-w-0 flex-1 basis-full sm:basis-auto text-left"
            onClick={() => onEdit(profile)}
          >
            <p className="truncate text-sm font-medium text-foreground">{profile.name}</p>
            <p className="truncate text-xs text-muted-foreground">{profile.id}</p>
          </button>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              disabled={activeProfileId === profile.id}
              aria-label={t('apply')}
              onClick={() => onApply(profile)}
              className={cn(
                'rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:text-foreground',
                activeProfileId === profile.id && 'opacity-50 pointer-events-none',
              )}
            >
              {t('apply')}
            </button>
            <button
              type="button"
              aria-label={t('delete')}
              className="rounded-md p-1.5 text-muted-foreground hover:text-destructive"
              onClick={() => onDelete(profile.id)}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
};

export default ProfileLibraryPanel;
