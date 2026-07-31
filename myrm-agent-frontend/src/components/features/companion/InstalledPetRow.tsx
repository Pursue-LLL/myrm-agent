'use client';

/**
 * InstalledPetRow — local-first chip row for Volume-installed pets.
 *
 * [INPUT]
 * - @/services/companion/petInstall::InstalledCompanionPet (POS: installed pet API shape)
 * - @/services/companion/petSpritesheet::companionPetSpritesheetUrl (POS: local spritesheet URL)
 * - PetGalleryThumb (POS: lazy gallery thumbnail)
 *
 * [OUTPUT]
 * - InstalledPetRow: clickable installed-pet chip grid with per-pet remove menu
 *
 * [POS]
 * Top section of PetGallery; switches active sprite without re-download.
 */

import { MoreHorizontal, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { PetGalleryThumb } from '@/components/features/companion/PetGalleryThumb';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import type { InstalledCompanionPet } from '@/services/companion/petInstall';
import { companionPetSpritesheetUrl } from '@/services/companion/petSpritesheet';
import { cn } from '@/lib/utils/classnameUtils';

interface InstalledPetRowProps {
  pets: InstalledCompanionPet[];
  currentSlug: string | undefined;
  activatingSlug: string | null;
  uninstallingSlug: string | null;
  onActivate: (pet: InstalledCompanionPet) => void;
  onRequestUninstall: (pet: InstalledCompanionPet) => void;
}

export function InstalledPetRow({
  pets,
  currentSlug,
  activatingSlug,
  uninstallingSlug,
  onActivate,
  onRequestUninstall,
}: InstalledPetRowProps) {
  const t = useTranslations('companion');

  if (pets.length === 0) return null;

  return (
    <div className="space-y-2" data-testid="pet-gallery-installed">
      <p className="text-xs font-medium text-foreground">{t('gallery.installedTitle')}</p>
      <div className="flex flex-wrap gap-2">
        {pets.map((pet) => {
          const isActive = currentSlug === pet.slug;
          const isActivating = activatingSlug === pet.slug;
          const isUninstalling = uninstallingSlug === pet.slug;
          const isBusy = isActivating || isUninstalling;
          const label = pet.display_name || pet.slug;
          return (
            <div
              key={pet.slug}
              className={cn(
                'group relative flex flex-col items-center gap-1 rounded-lg p-1.5 transition-all min-w-[72px]',
                isActive ? 'bg-primary/15 ring-1 ring-primary' : 'hover:bg-muted',
                isBusy && 'opacity-60',
              )}
            >
              {isBusy && (
                <div className="absolute inset-0 z-10 flex items-center justify-center">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                </div>
              )}
              <button
                type="button"
                onClick={() => onActivate(pet)}
                disabled={isBusy}
                title={label}
                data-testid={`installed-pet-${pet.slug}`}
                className={cn(
                  'flex w-full flex-col items-center gap-1',
                  isBusy && 'cursor-wait',
                )}
              >
                <PetGalleryThumb url={companionPetSpritesheetUrl(pet.slug)} alt={label} />
                <span className="w-full truncate text-center text-[10px] leading-tight text-foreground">
                  {label}
                </span>
              </button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    disabled={isBusy}
                    aria-label={t('gallery.uninstall')}
                    data-testid={`installed-pet-menu-${pet.slug}`}
                    className={cn(
                      'absolute right-0 top-0 rounded-md p-0.5 text-muted-foreground',
                      'opacity-100 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100 focus:opacity-100',
                      'hover:bg-background/80 hover:text-foreground',
                      isBusy && 'pointer-events-none',
                    )}
                    onClick={(event) => event.stopPropagation()}
                  >
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-[140px]">
                  <DropdownMenuItem
                    className="gap-2 text-destructive focus:text-destructive"
                    data-testid={`installed-pet-uninstall-${pet.slug}`}
                    onClick={() => onRequestUninstall(pet)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    {t('gallery.uninstall')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        })}
      </div>
    </div>
  );
}
