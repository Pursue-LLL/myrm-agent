'use client';

import { useCallback, useEffect, useMemo, useState, Suspense } from 'react';
import Link from 'next/link';
import { flushSync } from 'react-dom';
import { useTranslations } from 'next-intl';
import { ArrowLeft, ArrowRight, Loader2, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import useConfigStore from '@/store/useConfigStore';
import useThemeStudioDraftStore, { type BuilderStep } from '@/store/useThemeStudioDraftStore';
import ThemeStudioStepPanels from '@/components/features/theme-studio/ThemeStudioStepPanels';
import ThemeStudioPreview, { type PreviewScene } from '@/components/features/theme-studio/preview/ThemeStudioPreview';
import ProfileLibraryPanel from '@/components/features/theme-studio/ProfileLibraryPanel';
import RecipeImportPanel from '@/components/features/theme-studio/RecipeImportPanel';
import ThemeStudioGalleryPanel from '@/components/features/theme-studio/ThemeStudioGalleryPanel';
import ThemeStudioCreatorPanel from '@/components/features/theme-studio/ThemeStudioCreatorPanel';
import ThemeStudioAdminPanel from '@/components/features/theme-studio/ThemeStudioAdminPanel';
import { useThemeStudioDomPreview } from '@/components/features/theme-studio/hooks/useThemeStudioDomPreview';
import {
  allocateStudioProfileId,
  createStudioDraft,
  mergeProfileIntoLibrary,
  STUDIO_PREVIEW_PROFILE_ID,
} from '@/components/features/theme-studio/studio-profile';
import {
  downloadThemePackageBlob,
  exportThemePackage,
} from '@/services/theme-packages/exportThemePackage';
import { resolveThemeAssetUrl } from '@/services/theme-assets/ThemeAssetStore';
import {
  EMPTY_THEME_PROFILES,
  stripArtOverlay,
  type ThemeProfileRecipe,
} from '@/theme-engine';
import { listSkills } from '@/services/skill';

const STEPS: BuilderStep[] = [1, 2, 3, 4];

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [delayMs, value]);
  return debounced;
}

const ThemeStudioSection = () => {
  const t = useTranslations('settings.themeStudio');
  const draft = useThemeStudioDraftStore((state) => state.draft);
  const step = useThemeStudioDraftStore((state) => state.step);
  const previewAssetUrl = useThemeStudioDraftStore((state) => state.previewAssetUrl);
  const editingProfileId = useThemeStudioDraftStore((state) => state.editingProfileId);
  const setStep = useThemeStudioDraftStore((state) => state.setStep);
  const patchDraft = useThemeStudioDraftStore((state) => state.patchDraft);
  const replaceDraft = useThemeStudioDraftStore((state) => state.replaceDraft);
  const setPreviewAssetUrl = useThemeStudioDraftStore((state) => state.setPreviewAssetUrl);
  const hydrateFromStorage = useThemeStudioDraftStore((state) => state.hydrateFromStorage);
  const resetDraft = useThemeStudioDraftStore((state) => state.resetDraft);

  const themeProfiles = useConfigStore(
    (state) => state.personalSettings?.themeProfiles ?? EMPTY_THEME_PROFILES,
  );
  const activeThemeProfileId = useConfigStore(
    (state) => state.personalSettings?.activeThemeProfileId,
  );
  const updatePersonalSettings = useConfigStore((state) => state.updatePersonalSettings);

  const [previewScene, setPreviewScene] = useState<PreviewScene>('chat');
  const [livePreview, setLivePreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hasAiSkill, setHasAiSkill] = useState(false);

  const debouncedDraft = useDebouncedValue(draft, 150);

  useEffect(() => {
    hydrateFromStorage();
  }, [hydrateFromStorage]);

  useEffect(() => {
    let cancelled = false;
    void listSkills({ type: 'prebuilt' })
      .then((response) => {
        if (cancelled) {
          return;
        }
        const found = response.skills.some(
          (skill) => skill.id === 'generate-myrm-theme' || skill.id.endsWith('/generate-myrm-theme'),
        );
        setHasAiSkill(found);
      })
      .catch(() => {
        if (!cancelled) {
          setHasAiSkill(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadPreview = async () => {
      if (!draft.art.assetRef) {
        setPreviewAssetUrl(null);
        return;
      }
      const url = await resolveThemeAssetUrl(
        draft.art.mediaKind === 'video'
          ? (draft.art.posterAssetRef ?? draft.art.assetRef)
          : draft.art.assetRef,
      );
      if (!cancelled) {
        setPreviewAssetUrl(url);
      }
    };
    void loadPreview();
    return () => {
      cancelled = true;
    };
  }, [draft.art.assetRef, draft.art.mediaKind, draft.art.posterAssetRef, setPreviewAssetUrl]);

  const previewProfile = useMemo(() => debouncedDraft, [debouncedDraft]);
  useThemeStudioDomPreview(livePreview && !busy, previewProfile, previewAssetUrl);

  const buildFinalProfile = useCallback((): ThemeProfileRecipe => {
    const profileId = editingProfileId ?? allocateStudioProfileId();
    return {
      ...draft,
      id: profileId,
      name: draft.name.trim() || t('defaultThemeName'),
      builtin: false,
    };
  }, [draft, editingProfileId, t]);

  const handleApply = useCallback(async () => {
    flushSync(() => {
      setBusy(true);
      setLivePreview(false);
    });
    try {
      const finalProfile = buildFinalProfile();
      const cleaned = stripArtOverlay(
        themeProfiles.filter((profile) => profile.id !== STUDIO_PREVIEW_PROFILE_ID),
      );
      await updatePersonalSettings({
        themeProfiles: mergeProfileIntoLibrary(cleaned, finalProfile),
        activeThemeProfileId: finalProfile.id,
        themeFontOverride: finalProfile.fontId,
      });
      toast.success(t('applySuccess'));
      resetDraft();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('applyFailed'));
    } finally {
      setBusy(false);
    }
  }, [buildFinalProfile, resetDraft, t, themeProfiles, updatePersonalSettings]);

  const handleExport = useCallback(async () => {
    flushSync(() => {
      setBusy(true);
      setLivePreview(false);
    });
    try {
      const finalProfile = buildFinalProfile();
      const blob = await exportThemePackage(finalProfile);
      const safeName = finalProfile.name.replace(/[^\w\-]+/g, '-').slice(0, 48) || 'theme';
      downloadThemePackageBlob(blob, `${safeName}.myrmtheme`);
      toast.success(t('exportSuccess'));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('exportFailed'));
    } finally {
      setBusy(false);
    }
  }, [buildFinalProfile, t]);

  const handleApplyProfile = useCallback(
    async (profile: ThemeProfileRecipe) => {
      flushSync(() => {
        setBusy(true);
        setLivePreview(false);
      });
      try {
        await updatePersonalSettings({
          activeThemeProfileId: profile.id,
          themeFontOverride: profile.fontId,
          themeProfiles: stripArtOverlay(
            themeProfiles.filter((entry) => entry.id !== STUDIO_PREVIEW_PROFILE_ID),
          ),
        });
        toast.success(t('library.applied'));
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('applyFailed'));
      } finally {
        setBusy(false);
      }
    },
    [t, themeProfiles, updatePersonalSettings],
  );

  const handleDeleteProfile = useCallback(
    async (profileId: string) => {
      const nextProfiles = themeProfiles.filter((profile) => profile.id !== profileId);
      await updatePersonalSettings({
        themeProfiles: nextProfiles,
        ...(activeThemeProfileId === profileId
          ? { activeThemeProfileId: 'official-default' }
          : {}),
      });
      toast.success(t('library.deleted'));
    },
    [activeThemeProfileId, t, themeProfiles, updatePersonalSettings],
  );

  const handleEditProfile = useCallback(
    (profile: ThemeProfileRecipe) => {
      replaceDraft(createStudioDraft(profile), profile.id);
    },
    [replaceDraft],
  );

  const handleRecipeImport = useCallback(
    (patch: Partial<ThemeProfileRecipe>) => {
      patchDraft({
        ...patch,
        art: patch.art ? { ...draft.art, ...patch.art } : draft.art,
        palette: patch.palette ? { ...draft.palette, ...patch.palette } : draft.palette,
      });
    },
    [draft.art, draft.palette, patchDraft],
  );

  const canGoNext =
    step === 1 ? draft.art.mediaKind !== 'none' && Boolean(draft.art.assetRef) : true;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{t('title')}</h2>
          <p className="text-sm text-muted-foreground">{t('subtitle')}</p>
        </div>
        {hasAiSkill ? (
          <Link
            href="/settings/skills?sub=prebuilt"
            className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
          >
            <Sparkles className="h-4 w-4" />
            {t('openAiSkill')}
          </Link>
        ) : null}
      </div>

      <ol className="flex flex-wrap gap-2">
        {STEPS.map((value) => (
          <li key={value}>
            <button
              type="button"
              onClick={() => setStep(value)}
              className={cn(
                'rounded-full px-3 py-1 text-xs font-medium border',
                step === value
                  ? 'border-primary bg-primary/10 text-foreground'
                  : 'border-border text-muted-foreground',
              )}
            >
              {t(`steps.${value}` as 'steps.1')}
            </button>
          </li>
        ))}
      </ol>

      <Suspense fallback={null}>
        <ThemeStudioGalleryPanel />
      </Suspense>
      <ThemeStudioCreatorPanel />
      <ThemeStudioAdminPanel />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
        <div className="space-y-4">
          <ThemeStudioStepPanels
            step={step}
            draft={draft}
            onPatchDraft={patchDraft}
            onMediaUploaded={({ assetRef, mediaKind, posterAssetRef, previewUrl }) => {
              patchDraft({
                art: {
                  ...draft.art,
                  assetRef,
                  mediaKind,
                  posterAssetRef: posterAssetRef ?? null,
                },
              });
              setPreviewAssetUrl(previewUrl);
            }}
          />
          {step === 1 ? <RecipeImportPanel onImport={handleRecipeImport} /> : null}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={step === 1 || busy}
              onClick={() => setStep((step - 1) as BuilderStep)}
              className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-sm"
            >
              <ArrowLeft className="h-4 w-4" />
              {t('back')}
            </button>
            {step < 4 ? (
              <button
                type="button"
                disabled={!canGoNext || busy}
                onClick={() => setStep((step + 1) as BuilderStep)}
                className="inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
              >
                {t('next')}
                <ArrowRight className="h-4 w-4" />
              </button>
            ) : (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handleApply()}
                  className="inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
                >
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {t('apply')}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handleExport()}
                  className="rounded-lg border border-border px-3 py-2 text-sm"
                >
                  {t('export')}
                </button>
              </>
            )}
          </div>

          {step === 4 ? (
            <div className="space-y-2 border-t border-border pt-4">
              <p className="text-xs font-medium text-muted-foreground">{t('library.title')}</p>
              <ProfileLibraryPanel
                profiles={themeProfiles}
                activeProfileId={activeThemeProfileId}
                onEdit={handleEditProfile}
                onApply={(profile) => void handleApplyProfile(profile)}
                onDelete={(profileId) => void handleDeleteProfile(profileId)}
              />
            </div>
          ) : null}
        </div>

        <aside className="space-y-3">
          <div className="flex flex-wrap gap-1">
            {(['chat', 'kanban', 'settings', 'workDense'] as PreviewScene[]).map((scene) => (
              <button
                key={scene}
                type="button"
                onClick={() => setPreviewScene(scene)}
                className={cn(
                  'rounded-md px-2 py-1 text-xs border',
                  previewScene === scene
                    ? 'border-primary bg-primary/10'
                    : 'border-border text-muted-foreground',
                )}
              >
                {t(`preview.scene.${scene}`)}
              </button>
            ))}
          </div>
          <ThemeStudioPreview
            draft={debouncedDraft}
            previewAssetUrl={previewAssetUrl}
            scene={previewScene}
          />
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={livePreview}
              onChange={(event) => setLivePreview(event.target.checked)}
            />
            {t('livePreview')}
          </label>
        </aside>
      </div>
    </div>
  );
};

export default ThemeStudioSection;
