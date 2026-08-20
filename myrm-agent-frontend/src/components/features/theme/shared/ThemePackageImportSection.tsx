'use client';

/**
 * [INPUT]
 * - services/theme-packages inspect/install/export
 * - store/useConfigStore personalSettings.themeProfiles
 *
 * [OUTPUT]
 * - ThemePackageImportSection
 *
 * [POS]
 * Shared `.myrmtheme` import/export block for Appearance and Theme Studio Step 4.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, Package, Upload } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import useConfigStore from '@/store/useConfigStore';
import useThemePackagePendingStore from '@/store/useThemePackagePendingStore';
import ThemePackageImportPreview from '@/components/features/theme/ThemePackageImportPreview';
import { inspectThemePackage } from '@/services/theme-packages/inspectThemePackage';
import type { ThemePackageInspectResult } from '@/services/theme-packages/inspectThemePackage';
import { installThemePackage } from '@/services/theme-packages/installThemePackage';
import { downloadThemePackageBlob, exportThemePackage } from '@/services/theme-packages/exportThemePackage';
import { BUILTIN_THEME_PROFILES, stripArtOverlay, type ThemeProfileRecipe } from '@/theme-engine';

interface ThemePackageImportSectionProps {
  className?: string;
  disabled?: boolean;
  showExport?: boolean;
  exportProfile?: ThemeProfileRecipe;
  /** When true, strip art overlay profiles before merging imported profile (Appearance fast path). */
  stripOverlayOnImport?: boolean;
}

/** Stable fallback — never inline `?? []` in Zustand selectors (new array each snapshot). */
const EMPTY_THEME_PROFILES: ThemeProfileRecipe[] = [];

const ThemePackageImportSection = ({
  className,
  disabled = false,
  showExport = true,
  exportProfile,
  stripOverlayOnImport = false,
}: ThemePackageImportSectionProps) => {
  const t = useTranslations('settings.appearancePanel');
  const themeProfilesRaw = useConfigStore((state) => state.personalSettings?.themeProfiles);
  const themeProfiles = themeProfilesRaw ?? EMPTY_THEME_PROFILES;
  const updatePersonalSettings = useConfigStore((state) => state.updatePersonalSettings);

  const packageInputRef = useRef<HTMLInputElement>(null);
  const [packageBusy, setPackageBusy] = useState(false);
  const [packageInspect, setPackageInspect] = useState<ThemePackageInspectResult | null>(null);
  const [packagePreviewOpen, setPackagePreviewOpen] = useState(false);
  const pendingPackageFile = useThemePackagePendingStore((state) => state.pendingFile);
  const clearPendingPackageFile = useThemePackagePendingStore((state) => state.clearPendingFile);

  useEffect(() => {
    if (!pendingPackageFile) {
      return;
    }
    let cancelled = false;
    const run = async () => {
      setPackageBusy(true);
      try {
        const inspect = await inspectThemePackage(pendingPackageFile);
        if (cancelled) {
          return;
        }
        setPackageInspect(inspect);
        setPackagePreviewOpen(true);
      } catch (error) {
        if (!cancelled) {
          toast.error(error instanceof Error ? error.message : t('packageImportFailed'));
        }
      } finally {
        if (!cancelled) {
          setPackageBusy(false);
          clearPendingPackageFile();
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [clearPendingPackageFile, pendingPackageFile, t]);

  const handleExportPackage = useCallback(async () => {
    if (!exportProfile) {
      return;
    }
    setPackageBusy(true);
    try {
      const blob = await exportThemePackage(exportProfile);
      const safeName = exportProfile.name.replace(/[^\w-]+/g, '-').slice(0, 48) || 'workspace-theme';
      downloadThemePackageBlob(blob, `${safeName}.myrmtheme`);
      toast.success(t('packageExportSuccess'));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('packageExportFailed'));
    } finally {
      setPackageBusy(false);
    }
  }, [exportProfile, t]);

  const handlePackageSelected = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) {
        return;
      }
      setPackageBusy(true);
      try {
        const inspect = await inspectThemePackage(file);
        setPackageInspect(inspect);
        setPackagePreviewOpen(true);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('packageImportFailed'));
      } finally {
        setPackageBusy(false);
      }
    },
    [t],
  );

  const handleConfirmPackageImport = useCallback(async () => {
    if (!packageInspect) {
      return;
    }
    setPackageBusy(true);
    try {
      const existingIds = [
        ...BUILTIN_THEME_PROFILES.map((profile) => profile.id),
        ...themeProfiles.map((profile) => profile.id),
      ];
      const { profile, setActive } = await installThemePackage({
        sessionId: packageInspect.sessionId,
        setActive: true,
        existingProfileIds: existingIds,
      });
      let nextProfiles = themeProfiles;
      if (stripOverlayOnImport) {
        nextProfiles = themeProfiles.filter((entry) => !entry.id.startsWith('imported/'));
        nextProfiles = stripArtOverlay(nextProfiles);
      }
      await updatePersonalSettings({
        themeProfiles: [...nextProfiles, profile],
        ...(setActive
          ? {
              activeThemeProfileId: profile.id,
              themeFontOverride: profile.fontId,
            }
          : {}),
      });
      setPackagePreviewOpen(false);
      setPackageInspect(null);
      toast.success(t('packageImportSuccess'));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('packageImportFailed'));
    } finally {
      setPackageBusy(false);
    }
  }, [packageInspect, stripOverlayOnImport, t, themeProfiles, updatePersonalSettings]);

  const busy = disabled || packageBusy;

  return (
    <div className={cn('space-y-2', className)}>
      <p className="text-xs font-medium text-muted-foreground">{t('packageSection')}</p>
      <p className="text-xs text-muted-foreground/80">{t('packageSectionDesc')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={packageInputRef}
          type="file"
          accept=".myrmtheme,application/zip"
          className="hidden"
          onChange={handlePackageSelected}
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => packageInputRef.current?.click()}
          className={cn(
            'inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-all',
            'border-border bg-secondary/40 text-muted-foreground hover:text-foreground',
            busy && 'opacity-60 pointer-events-none',
          )}
        >
          {packageBusy ? (
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
          ) : (
            <Package className="w-4 h-4" aria-hidden />
          )}
          {t('packageImport')}
        </button>
        {showExport && exportProfile ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => void handleExportPackage()}
            className={cn(
              'inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-all',
              'border-border bg-secondary/40 text-muted-foreground hover:text-foreground',
              busy && 'opacity-60 pointer-events-none',
            )}
          >
            <Upload className="w-4 h-4" aria-hidden />
            {t('packageExport')}
          </button>
        ) : null}
      </div>

      <ThemePackageImportPreview
        open={packagePreviewOpen}
        inspect={packageInspect}
        busy={packageBusy}
        onClose={() => {
          setPackagePreviewOpen(false);
          setPackageInspect(null);
        }}
        onConfirm={() => void handleConfirmPackageImport()}
      />
    </div>
  );
};

export default ThemePackageImportSection;
