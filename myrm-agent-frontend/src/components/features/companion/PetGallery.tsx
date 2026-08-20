'use client';

/**
 * PetGallery — Visual gallery for browsing and installing Petdex community pets.
 *
 * [INPUT]
 * - useCompanionStore (POS: Companion state with sprite config)
 * - listInstalledCompanionPets / installCompanionPet (POS: companion pet API)
 * - InstalledPetRow (POS: local-first installed chip row)
 * - petGalleryManifest::fetchPetdexManifest (POS: public manifest loader)
 *
 * [OUTPUT]
 * - PetGallery: Installed row + manifest catalog + uninstall confirm flow
 *
 * [POS]
 * Local installed pets from GET /companion/pets render immediately; syncs with store
 * spriteConfig for slash/catalog install paths. Public manifest is best-effort.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { InstalledPetRow } from '@/components/features/companion/InstalledPetRow';
import { PetGalleryThumb } from '@/components/features/companion/PetGalleryThumb';
import {
  fetchPetdexManifest,
  rankManifestPets,
  petdexPetPageUrl,
  type ManifestPet,
} from '@/components/features/companion/petGalleryManifest';
import { CompanionPetDoctorPanel } from '@/components/features/companion/CompanionPetDoctorPanel';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Input } from '@/components/primitives/input';
import {
  installCompanionPet,
  listInstalledCompanionPets,
  uninstallCompanionPet,
  CompanionFeatureDisabledError,
  type InstalledCompanionPet,
} from '@/services/companion/petInstall';
import { cn } from '@/lib/utils/classnameUtils';
import useCompanionStore from '@/store/useCompanionStore';

const PAGE_SIZE = 60;

interface PetGalleryProps {
  /** When true, refetch GET /companion/pets (e.g. PetPalette open). */
  reloadInstalledWhen?: boolean;
}

function mergeInstalledPet(
  prev: InstalledCompanionPet[],
  next: Partial<InstalledCompanionPet> & Pick<InstalledCompanionPet, 'slug'>,
): InstalledCompanionPet[] {
  const existing = prev.find((item) => item.slug === next.slug);
  const merged: InstalledCompanionPet = {
    slug: next.slug,
    display_name: next.display_name ?? existing?.display_name ?? next.slug,
    content_sha256: next.content_sha256 ?? existing?.content_sha256 ?? '',
    format_label: next.format_label ?? existing?.format_label,
    format_tier: next.format_tier ?? existing?.format_tier,
  };
  const without = prev.filter((item) => item.slug !== next.slug);
  return [...without, merged];
}

export default function PetGallery({ reloadInstalledWhen = true }: PetGalleryProps) {
  const t = useTranslations('companion');
  const setSpriteConfig = useCompanionStore((s) => s.setSpriteConfig);
  const setSpriteEnabled = useCompanionStore((s) => s.setSpriteEnabled);
  const saveConfigToServer = useCompanionStore((s) => s.saveConfigToServer);
  const spriteConfig = useCompanionStore((s) => s.spriteConfig);
  const currentSlug = spriteConfig?.petSlug;
  const doctorExpandPending = useCompanionStore((s) => s.doctorExpandPending);
  const clearDoctorExpandPending = useCompanionStore((s) => s.clearDoctorExpandPending);

  const [installedPets, setInstalledPets] = useState<InstalledCompanionPet[]>([]);
  const [installedLoading, setInstalledLoading] = useState(true);
  const [manifestPets, setManifestPets] = useState<ManifestPet[]>([]);
  const [manifestLoading, setManifestLoading] = useState(true);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [uninstallError, setUninstallError] = useState<string | null>(null);
  const [installingSlug, setInstallingSlug] = useState<string | null>(null);
  const [activatingSlug, setActivatingSlug] = useState<string | null>(null);
  const [uninstallingSlug, setUninstallingSlug] = useState<string | null>(null);
  const [pendingUninstall, setPendingUninstall] = useState<InstalledCompanionPet | null>(null);
  const [uninstallDialogOpen, setUninstallDialogOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [doctorExpanded, setDoctorExpanded] = useState(false);

  const sentinelRef = useRef<HTMLDivElement>(null);
  const installedFetchGenRef = useRef(0);

  const fetchInstalledPets = useCallback(() => {
    const generation = ++installedFetchGenRef.current;
    setInstalledLoading(true);
    listInstalledCompanionPets()
      .then((pets) => {
        if (generation !== installedFetchGenRef.current) {
          return;
        }
        setInstalledPets(pets);
      })
      .catch(() => {
        if (generation !== installedFetchGenRef.current) {
          return;
        }
        setInstalledPets([]);
      })
      .finally(() => {
        if (generation !== installedFetchGenRef.current) {
          return;
        }
        setInstalledLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!reloadInstalledWhen) {
      return;
    }
    fetchInstalledPets();
  }, [reloadInstalledWhen, fetchInstalledPets]);

  useEffect(() => {
    const slug = spriteConfig?.petSlug;
    if (!slug) {
      return;
    }
    setInstalledPets((prev) =>
      mergeInstalledPet(prev, {
        slug,
        display_name: spriteConfig.displayName ?? slug,
        content_sha256: spriteConfig.contentSha256 ?? '',
      }),
    );
    fetchInstalledPets();
  }, [spriteConfig?.petSlug, spriteConfig?.contentSha256, spriteConfig?.displayName, fetchInstalledPets]);

  useEffect(() => {
    let cancelled = false;
    setManifestLoading(true);
    setManifestError(null);
    fetchPetdexManifest()
      .then((data) => {
        if (!cancelled) {
          setManifestPets(data);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setManifestError(String(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setManifestLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!doctorExpandPending) {
      return;
    }
    setDoctorExpanded(true);
    clearDoctorExpandPending();
  }, [doctorExpandPending, clearDoctorExpandPending]);

  const filtered = useMemo(() => {
    const installedSlugs = new Set(installedPets.map((p) => p.slug));
    const ranked = rankManifestPets(manifestPets, {
      installedSlugs,
      activeSlug: currentSlug,
    });
    if (!search.trim()) {
      return ranked;
    }
    const q = search.trim().toLowerCase();
    return ranked.filter((p) => p.slug.toLowerCase().includes(q) || p.displayName.toLowerCase().includes(q));
  }, [manifestPets, installedPets, currentSlug, search]);

  const visible = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) {
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisibleCount((prev) => Math.min(prev + PAGE_SIZE, filtered.length));
      }
    });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [filtered.length]);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [search]);

  const persistSpriteSelection = useCallback(() => {
    void saveConfigToServer();
  }, [saveConfigToServer]);

  const handleActivateInstalled = useCallback(
    (pet: InstalledCompanionPet) => {
      setInstallError(null);
      setActivatingSlug(pet.slug);
      setSpriteConfig({
        petSlug: pet.slug,
        displayName: pet.display_name,
        contentSha256: pet.content_sha256,
      });
      setSpriteEnabled(true);
      persistSpriteSelection();
      setActivatingSlug(null);
    },
    [persistSpriteSelection, setSpriteConfig, setSpriteEnabled],
  );

  const handleInstall = useCallback(
    async (pet: ManifestPet) => {
      setInstallError(null);
      setUninstallError(null);
      setInstallingSlug(pet.slug);
      try {
        const installed = await installCompanionPet(pet.slug);
        setSpriteConfig({
          petSlug: installed.slug,
          displayName: installed.display_name,
          contentSha256: installed.content_sha256,
        });
        setSpriteEnabled(true);
        setInstalledPets((prev) => mergeInstalledPet(prev, installed));
        persistSpriteSelection();
      } catch (err) {
        if (err instanceof CompanionFeatureDisabledError) {
          setInstallError(t('gallery.companionGateError'));
        } else {
          setInstallError(String(err instanceof Error ? err.message : err));
        }
      } finally {
        setInstallingSlug(null);
      }
    },
    [persistSpriteSelection, setSpriteConfig, setSpriteEnabled],
  );

  const handleRequestUninstall = useCallback((pet: InstalledCompanionPet) => {
    setUninstallError(null);
    setPendingUninstall(pet);
    setUninstallDialogOpen(true);
  }, []);

  const handleConfirmUninstall = useCallback(async () => {
    setUninstallDialogOpen(false);
    if (!pendingUninstall) {
      return;
    }

    const pet = pendingUninstall;
    setPendingUninstall(null);
    setUninstallError(null);
    setUninstallingSlug(pet.slug);

    try {
      await uninstallCompanionPet(pet.slug);
      setInstalledPets((prev) => prev.filter((item) => item.slug !== pet.slug));
      if (currentSlug === pet.slug) {
        setSpriteConfig(null);
        setSpriteEnabled(false);
        persistSpriteSelection();
      }
    } catch (err) {
      setUninstallError(String(err instanceof Error ? err.message : err));
    } finally {
      setUninstallingSlug(null);
    }
  }, [currentSlug, pendingUninstall, persistSpriteSelection, setSpriteConfig, setSpriteEnabled]);

  const showFullPageLoading = installedLoading && manifestLoading && installedPets.length === 0 && !manifestError;
  const showManifestOfflineHint = Boolean(manifestError) && installedPets.length > 0;
  const showHardError = Boolean(manifestError) && !installedLoading && installedPets.length === 0;
  const showCatalog = !manifestError && manifestPets.length > 0;

  if (showFullPageLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <span className="ml-2 text-sm text-muted-foreground">{t('gallery.loading')}</span>
      </div>
    );
  }

  if (showHardError) {
    return <div className="py-6 text-center text-sm text-destructive">{t('gallery.error')}</div>;
  }

  return (
    <div className="space-y-4">
      <CompanionPetDoctorPanel expanded={doctorExpanded} onExpandedChange={setDoctorExpanded} />

      <InstalledPetRow
        pets={installedPets}
        currentSlug={currentSlug}
        activatingSlug={activatingSlug}
        uninstallingSlug={uninstallingSlug}
        onActivate={handleActivateInstalled}
        onRequestUninstall={handleRequestUninstall}
      />

      {showManifestOfflineHint && (
        <p className="text-xs text-muted-foreground leading-snug" data-testid="pet-gallery-offline-hint">
          {t('gallery.manifestOffline')}
        </p>
      )}

      {installError && <div className="text-xs text-destructive">{installError}</div>}

      {uninstallError && (
        <div className="text-xs text-destructive" data-testid="pet-gallery-uninstall-error">
          {uninstallError}
        </div>
      )}

      <AlertDialog
        open={uninstallDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            setUninstallDialogOpen(false);
            setPendingUninstall(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="h-5 w-5 text-destructive" />
              {t('gallery.uninstall')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('gallery.uninstallConfirm')}
              {pendingUninstall && (
                <span className="font-medium text-foreground">
                  {' '}
                  {pendingUninstall.display_name || pendingUninstall.slug}
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('gallery.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void handleConfirmUninstall()}
              className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              {t('gallery.uninstall')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {manifestLoading && !showCatalog && (
        <div className="flex items-center justify-center py-4">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
          <span className="ml-2 text-xs text-muted-foreground">{t('gallery.loading')}</span>
        </div>
      )}

      {showCatalog && (
        <div className="space-y-3">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('gallery.searchPlaceholder')}
            className="text-xs"
          />

          <div className="text-xs text-muted-foreground">{t('gallery.count', { count: filtered.length })}</div>

          <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-[320px] overflow-y-auto pr-1">
            {visible.map((pet) => {
              const isActive = currentSlug === pet.slug;
              const isInstalling = installingSlug === pet.slug;
              return (
                <div
                  key={pet.slug}
                  className={cn(
                    'relative flex flex-col items-center gap-0.5 rounded-lg p-1.5 transition-all',
                    isActive ? 'bg-primary/15 ring-1 ring-primary' : 'hover:bg-muted',
                    isInstalling && 'opacity-60',
                  )}
                >
                  <button
                    type="button"
                    onClick={() => handleInstall(pet)}
                    disabled={isInstalling}
                    title={pet.displayName}
                    className={cn('relative flex w-full flex-col items-center gap-1', isInstalling && 'cursor-wait')}
                  >
                    {isInstalling && (
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                      </div>
                    )}
                    <PetGalleryThumb url={pet.spritesheetUrl} alt={pet.displayName} />
                    {pet.curated && (
                      <span className="absolute left-0.5 top-0.5 rounded bg-primary/90 px-1 py-px text-[8px] font-medium text-primary-foreground">
                        {t('gallery.officialBadge')}
                      </span>
                    )}
                    <span className="w-full truncate text-center text-[10px] leading-tight text-foreground">
                      {pet.displayName}
                    </span>
                  </button>
                  <a
                    href={petdexPetPageUrl(pet.slug)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[9px] text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
                  >
                    {t('gallery.viewOnPetdex')}
                  </a>
                </div>
              );
            })}
          </div>

          {visibleCount < filtered.length && (
            <div ref={sentinelRef} className="flex justify-center py-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
