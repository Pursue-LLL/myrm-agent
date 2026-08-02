'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import ThemeMediaUploadField from '@/components/features/theme/shared/ThemeMediaUploadField';
import ThemePresetGrid from '@/components/features/theme/shared/ThemePresetGrid';
import { FONT_CHOICES } from '@/lib/fonts';
import {
  ART_WASH_MAX,
  ART_WASH_MIN,
  BUILTIN_THEME_PROFILES,
  THEME_LAYOUT_CATALOG,
  derivePalette,
  type ThemeProfileRecipe,
} from '@/theme-engine';
import type { BuilderStep } from '@/store/useThemeStudioDraftStore';

interface ThemeStudioStepPanelsProps {
  step: BuilderStep;
  draft: ThemeProfileRecipe;
  onPatchDraft: (patch: Partial<ThemeProfileRecipe>) => void;
  onMediaUploaded: (payload: {
    assetRef: string;
    mediaKind: 'image' | 'video';
    posterAssetRef?: string | null;
    previewUrl: string | null;
  }) => void;
}

const HEX_PATTERN = /^#[0-9a-fA-F]{6}$/;

const ThemeStudioStepPanels = ({
  step,
  draft,
  onPatchDraft,
  onMediaUploaded,
}: ThemeStudioStepPanelsProps) => {
  const t = useTranslations('settings.themeStudio');
  const tAppearance = useTranslations('settings.appearancePanel');
  const tFonts = useTranslations('settings.fontOptions');
  const tLayouts = useTranslations('settings.themeStudio.layouts');
  const [customHex, setCustomHex] = useState('');

  const handlePresetSelect = useCallback(
    (profileId: string) => {
      const preset = BUILTIN_THEME_PROFILES.find((entry) => entry.id === profileId);
      if (!preset) {
        return;
      }
      setCustomHex('');
      onPatchDraft({
        palette: { ...preset.palette },
        layoutId: preset.layoutId,
      });
    },
    [onPatchDraft],
  );

  if (step === 1) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">{t('steps.heroDesc')}</p>
        <ThemeMediaUploadField onUploaded={onMediaUploaded} />
        {draft.art.mediaKind !== 'none' ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-xs">
              <span className="text-muted-foreground">{t('focusX')}</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={draft.art.focusX}
                className="w-full accent-primary"
                onChange={(event) =>
                  onPatchDraft({
                    art: { ...draft.art, focusX: Number(event.target.value) },
                  })
                }
              />
            </label>
            <label className="space-y-1 text-xs">
              <span className="text-muted-foreground">{t('focusY')}</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={draft.art.focusY}
                className="w-full accent-primary"
                onChange={(event) =>
                  onPatchDraft({
                    art: { ...draft.art, focusY: Number(event.target.value) },
                  })
                }
              />
            </label>
          </div>
        ) : null}
      </div>
    );
  }

  if (step === 2) {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        {THEME_LAYOUT_CATALOG.map((layout) => (
          <button
            key={layout.id}
            type="button"
            onClick={() => onPatchDraft({ layoutId: layout.id })}
            className={cn(
              'rounded-xl border p-3 text-left transition-all',
              draft.layoutId === layout.id
                ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                : 'border-border hover:border-primary/40',
            )}
          >
            <p className="text-sm font-medium text-foreground">{tLayouts(layout.nameKey)}</p>
            <p className="mt-1 text-xs text-muted-foreground">{tLayouts(layout.descriptionKey)}</p>
            <p className="mt-2 text-xs text-muted-foreground/80">{tLayouts(layout.guidanceKey)}</p>
          </button>
        ))}
      </div>
    );
  }

  if (step === 3) {
    return (
      <div className="space-y-4">
        <ThemePresetGrid
          profiles={BUILTIN_THEME_PROFILES}
          activeProfileId={
            BUILTIN_THEME_PROFILES.find(
              (preset) =>
                preset.palette.primaryLight === draft.palette.primaryLight &&
                preset.palette.primaryDark === draft.palette.primaryDark,
            )?.id ?? BUILTIN_THEME_PROFILES[0].id
          }
          labelForProfile={(profile) => tAppearance(`presets.${profile.id}` as 'presets.official-default')}
          onSelect={handlePresetSelect}
        />
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <div className="h-px flex-1 bg-border" />
            <span className="text-xs text-muted-foreground">{tAppearance('customPrimaryColor')}</span>
            <div className="h-px flex-1 bg-border" />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={customHex || draft.palette.primaryLight}
              className="h-9 w-9 cursor-pointer rounded-md border border-border bg-transparent p-0.5"
              onChange={(e) => {
                const hex = e.target.value;
                setCustomHex(hex);
                onPatchDraft({ palette: derivePalette(hex) });
              }}
            />
            <input
              type="text"
              value={customHex}
              placeholder={tAppearance('hexPlaceholder')}
              maxLength={7}
              className={cn(
                'w-28 rounded-lg border bg-background px-3 py-2 font-mono text-sm',
                customHex.length === 7 && !HEX_PATTERN.test(customHex)
                  ? 'border-destructive'
                  : 'border-border',
              )}
              onChange={(e) => {
                const raw = e.target.value;
                setCustomHex(raw);
                if (HEX_PATTERN.test(raw)) {
                  onPatchDraft({ palette: derivePalette(raw) });
                }
              }}
            />
          </div>
        </div>
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">{tAppearance('font')}</p>
          <div className="flex flex-wrap gap-2">
            {FONT_CHOICES.map((font) => (
              <button
                key={font.id}
                type="button"
                onClick={() => onPatchDraft({ fontId: font.id })}
                className={cn(
                  'rounded-lg border px-3 py-2 text-sm transition-all',
                  draft.fontId === font.id
                    ? 'border-primary bg-primary/10 text-foreground'
                    : 'border-border bg-secondary/40 text-muted-foreground hover:text-foreground',
                )}
              >
                {tFonts(font.id)}
              </button>
            ))}
          </div>
        </div>
        <label className="block space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{tAppearance('backgroundWash')}</span>
            <span>{Math.round(draft.art.wash * 100)}%</span>
          </div>
          <input
            type="range"
            min={ART_WASH_MIN}
            max={ART_WASH_MAX}
            step={0.02}
            value={draft.art.wash}
            className="w-full accent-primary"
            onChange={(event) =>
              onPatchDraft({
                art: { ...draft.art, wash: Number(event.target.value) },
              })
            }
          />
        </label>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <label className="block space-y-1">
        <span className="text-xs font-medium text-muted-foreground">{t('themeName')}</span>
        <input
          type="text"
          value={draft.name}
          maxLength={256}
          placeholder={t('themeNamePlaceholder')}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          onChange={(event) => onPatchDraft({ name: event.target.value })}
        />
      </label>
      <label className="block space-y-1">
        <span className="text-xs font-medium text-muted-foreground">{t('tagline')}</span>
        <input
          type="text"
          value={draft.packageTagline ?? ''}
          maxLength={256}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          onChange={(event) => onPatchDraft({ packageTagline: event.target.value })}
        />
      </label>
    </div>
  );
};

export default ThemeStudioStepPanels;
