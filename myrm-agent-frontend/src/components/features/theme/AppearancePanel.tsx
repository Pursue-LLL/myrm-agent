'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { ImageIcon, Loader2, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import useConfigStore from '@/store/useConfigStore';
import ThemeProfilePicker from '@/components/features/theme/shared/ThemeProfilePicker';
import ThemePackageImportSection from '@/components/features/theme/shared/ThemePackageImportSection';
import SystemFontPicker from '@/components/features/theme/shared/SystemFontPicker';
import {
  ART_WASH_MAX,
  ART_WASH_MIN,
  BUILTIN_THEME_PROFILES,
  OFFICIAL_DEFAULT_PROFILE_ID,
  EMPTY_THEME_PROFILES,
  buildArtOverlayProfile,
  getArtOverlayProfile,
  hasArtOverlay,
  stripArtOverlay,
  updateArtOverlayWash,
  upsertArtOverlayProfile,
  validateThemeBackgroundFile,
  type ThemeBackgroundValidationError,
  type ThemeProfileRecipe,
} from '@/theme-engine';
import type { FontId } from '@/lib/fonts';
import { FONT_CHOICES } from '@/lib/fonts';
import {
  ThemeBackgroundValidationFailedError,
  uploadThemeBackground,
} from '@/services/theme-assets/uploadThemeBackground';
import { VideoPosterExtractionError } from '@/services/theme-assets/extractVideoPoster';
import {
  executeOfficialThemeRestore,
  shouldConfirmOfficialThemeRestore,
} from '@/components/features/theme/restoreOfficialTheme';
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

const ACCEPTED_BACKGROUND_TYPES = 'image/png,image/jpeg,image/webp,video/mp4,.png,.jpg,.jpeg,.webp,.mp4';

const VALIDATION_MESSAGE_KEYS: Record<
  ThemeBackgroundValidationError,
  'backgroundInvalidType' | 'backgroundTooLarge' | 'backgroundEmpty'
> = {
  invalidType: 'backgroundInvalidType',
  tooLarge: 'backgroundTooLarge',
  empty: 'backgroundEmpty',
};

const AppearancePanel = ({ className }: { className?: string }) => {
  const t = useTranslations('settings.appearancePanel');
  const tMenu = useTranslations('settings.menu');
  const tFonts = useTranslations('settings.fontOptions');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [restoreConfirmOpen, setRestoreConfirmOpen] = useState(false);

  const activeThemeProfileId = useConfigStore(
    (s) => s.personalSettings?.activeThemeProfileId ?? OFFICIAL_DEFAULT_PROFILE_ID,
  );
  const themeProfiles = useConfigStore((s) => s.personalSettings?.themeProfiles ?? EMPTY_THEME_PROFILES);
  const updatePersonalSettings = useConfigStore((s) => s.updatePersonalSettings);

  const activeProfile =
    BUILTIN_THEME_PROFILES.find((p) => p.id === activeThemeProfileId) ??
    themeProfiles.find((p) => p.id === activeThemeProfileId) ??
    BUILTIN_THEME_PROFILES[0];

  const backgroundActive = hasArtOverlay(themeProfiles);
  const artOverlay = getArtOverlayProfile(themeProfiles);
  const needsPosterReupload = artOverlay?.art.mediaKind === 'video' && !artOverlay.art.posterAssetRef;
  const persistedWash = artOverlay?.art.wash ?? activeProfile.art.wash;
  const [washDraft, setWashDraft] = useState(persistedWash);

  useEffect(() => {
    setWashDraft(persistedWash);
  }, [persistedWash]);

  const activeFontId = useConfigStore((s) => s.personalSettings?.themeFontOverride ?? activeProfile.fontId);

  const handleSelectProfile = useCallback(
    async (profileId: string) => {
      const selected =
        BUILTIN_THEME_PROFILES.find((profile) => profile.id === profileId) ??
        themeProfiles.find((profile) => profile.id === profileId);
      await updatePersonalSettings({
        activeThemeProfileId: profileId,
        ...(selected ? { themeFontOverride: selected.fontId } : {}),
      });
    },
    [themeProfiles, updatePersonalSettings],
  );

  const handleFontChange = useCallback(
    async (fontId: FontId) => {
      await updatePersonalSettings({ themeFontOverride: fontId });
    },
    [updatePersonalSettings],
  );

  const handleRestoreDefault = useCallback(async () => {
    try {
      await executeOfficialThemeRestore();
      toast.success(t('restoreSuccess'));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('restoreFailed'));
    }
  }, [t]);

  const handleRestoreClick = useCallback(() => {
    if (shouldConfirmOfficialThemeRestore()) {
      setRestoreConfirmOpen(true);
      return;
    }
    void handleRestoreDefault();
  }, [handleRestoreDefault]);

  const handleClearBackground = useCallback(async () => {
    await updatePersonalSettings({
      themeProfiles: stripArtOverlay(themeProfiles),
    });
  }, [themeProfiles, updatePersonalSettings]);

  const handleBackgroundSelected = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) {
        return;
      }

      const validationError = validateThemeBackgroundFile(file);
      if (validationError) {
        toast.error(t(VALIDATION_MESSAGE_KEYS[validationError]));
        return;
      }

      setUploading(true);
      try {
        const { assetRef, mediaKind, posterAssetRef } = await uploadThemeBackground(file);

        const overlay = buildArtOverlayProfile(activeProfile, assetRef, mediaKind, posterAssetRef);
        await updatePersonalSettings({
          themeProfiles: upsertArtOverlayProfile(themeProfiles, overlay),
        });
        toast.success(t('backgroundUploadSuccess'));
      } catch (error) {
        const message =
          error instanceof ThemeBackgroundValidationFailedError
            ? t(VALIDATION_MESSAGE_KEYS[error.code])
            : error instanceof VideoPosterExtractionError
              ? t('backgroundPosterFailed')
              : error instanceof Error
                ? error.message
                : t('backgroundUploadFailed');
        toast.error(message);
      } finally {
        setUploading(false);
      }
    },
    [activeProfile, t, themeProfiles, updatePersonalSettings],
  );

  const commitWash = useCallback(
    async (wash: number) => {
      if (Math.abs(wash - persistedWash) < 0.001) {
        return;
      }
      await updatePersonalSettings({
        themeProfiles: updateArtOverlayWash(themeProfiles, wash),
      });
    },
    [persistedWash, themeProfiles, updatePersonalSettings],
  );

  const buildExportProfile = useCallback((): ThemeProfileRecipe => {
    if (artOverlay) {
      return {
        ...activeProfile,
        name: activeProfile.name,
        art: { ...artOverlay.art },
      };
    }
    return activeProfile;
  }, [activeProfile, artOverlay]);

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      <p className="text-xs font-medium text-muted-foreground">{t('workspaceTheme')}</p>
      <ThemeProfilePicker
        themeProfiles={themeProfiles}
        activeProfileId={activeThemeProfileId}
        onSelect={handleSelectProfile}
      />

      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1">{t('workspaceBackground')}</p>
        <p className="text-xs text-muted-foreground/80 mb-2">{t('workspaceBackgroundDesc')}</p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_BACKGROUND_TYPES}
            className="hidden"
            onChange={handleBackgroundSelected}
          />
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              'inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-all',
              'border-border bg-secondary/40 text-muted-foreground hover:text-foreground',
              uploading && 'opacity-60 pointer-events-none',
            )}
          >
            {uploading ? (
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
            ) : (
              <ImageIcon className="w-4 h-4" aria-hidden />
            )}
            {backgroundActive ? t('changeBackground') : t('uploadBackground')}
          </button>
          {backgroundActive ? (
            <button
              type="button"
              disabled={uploading}
              onClick={handleClearBackground}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm border border-border text-muted-foreground hover:text-foreground transition-all"
            >
              <Trash2 className="w-4 h-4" aria-hidden />
              {t('clearBackground')}
            </button>
          ) : null}
        </div>
        {needsPosterReupload ? (
          <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">{t('backgroundPosterReupload')}</p>
        ) : null}
        {backgroundActive ? (
          <div className="mt-3 space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-medium text-muted-foreground">{t('backgroundWash')}</p>
              <span className="text-xs tabular-nums text-muted-foreground">{Math.round(washDraft * 100)}%</span>
            </div>
            <input
              type="range"
              min={ART_WASH_MIN}
              max={ART_WASH_MAX}
              step={0.02}
              value={washDraft}
              aria-label={t('backgroundWash')}
              className="w-full accent-primary h-1.5 cursor-pointer"
              onChange={(event) => setWashDraft(Number(event.target.value))}
              onPointerUp={() => void commitWash(washDraft)}
              onBlur={() => void commitWash(washDraft)}
              onKeyUp={(event) => {
                if (event.key === 'Enter') {
                  void commitWash(washDraft);
                }
              }}
            />
            <p className="text-xs text-muted-foreground/80">{t('backgroundWashDesc')}</p>
          </div>
        ) : null}
      </div>

      <div>
        <p className="text-xs font-medium text-muted-foreground mb-2">{t('font')}</p>
        <SystemFontPicker activeFontId={activeFontId} onFontChange={handleFontChange} />
      </div>
      <button
        type="button"
        onClick={handleRestoreClick}
        className="self-start text-sm text-muted-foreground hover:text-foreground underline-offset-4 hover:underline"
      >
        {t('restoreDefault')}
      </button>

      <Link
        href="/settings/theme-studio"
        className="self-start text-sm font-medium text-primary hover:underline underline-offset-4"
      >
        {tMenu('themeStudio')}
      </Link>

      <ThemePackageImportSection
        className="border-t border-border pt-4"
        disabled={uploading}
        exportProfile={buildExportProfile()}
        stripOverlayOnImport
      />

      <AlertDialog open={restoreConfirmOpen} onOpenChange={setRestoreConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('restoreConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('restoreConfirmDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('restoreCancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setRestoreConfirmOpen(false);
                void handleRestoreDefault();
              }}
            >
              {t('restoreConfirmAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default AppearancePanel;
