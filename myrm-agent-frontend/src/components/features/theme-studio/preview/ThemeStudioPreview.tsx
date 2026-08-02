'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTheme } from 'next-themes';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import {
  compileThemeProfile,
  resolveLayoutFromPathname,
  type ThemeProfileRecipe,
} from '@/theme-engine';

export type PreviewScene = 'chat' | 'kanban' | 'settings' | 'workDense';

interface ThemeStudioPreviewProps {
  draft: ThemeProfileRecipe;
  previewAssetUrl: string | null;
  scene: PreviewScene;
  compact?: boolean;
}

const ThemeStudioPreview = ({
  draft,
  previewAssetUrl,
  scene,
  compact = false,
}: ThemeStudioPreviewProps) => {
  const t = useTranslations('settings.themeStudio.preview');
  const { resolvedTheme } = useTheme();
  const colorScheme = resolvedTheme === 'light' ? 'light' : 'dark';
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const layoutId = useMemo(() => {
    if (scene === 'workDense') {
      return 'work-dense' as const;
    }
    if (scene === 'kanban') {
      return resolveLayoutFromPathname('/kanban', draft.layoutId);
    }
    if (scene === 'settings') {
      return resolveLayoutFromPathname('/settings/preferences', draft.layoutId);
    }
    return draft.layoutId;
  }, [draft.layoutId, scene]);

  const compiled = useMemo(() => {
    if (!mounted) {
      return null;
    }
    return compileThemeProfile(
      draft,
      {
        colorScheme,
        layoutId,
        prefersReducedMotion: false,
        isMobile: compact,
      },
      {
        mediaUrl: previewAssetUrl,
        posterUrl: previewAssetUrl,
      },
    );
  }, [colorScheme, compact, draft, layoutId, mounted, previewAssetUrl]);

  if (!compiled) {
    return (
      <div className="rounded-xl border border-border bg-secondary/20 h-64 animate-pulse" />
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{t(`scene.${scene}`)}</p>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground/70">
          {layoutId}
        </span>
      </div>
      <div
        className={cn(
          'relative overflow-hidden rounded-xl border border-border',
          compact ? 'h-48' : 'h-72',
        )}
        style={compiled.cssVariables as React.CSSProperties}
      >
        {compiled.artLayer.enabled && previewAssetUrl ? (
          <div
            className="absolute inset-0 bg-cover bg-center opacity-90"
            style={{
              backgroundImage: `url("${previewAssetUrl}")`,
              backgroundPosition: `${draft.art.focusX * 100}% ${draft.art.focusY * 100}%`,
            }}
          />
        ) : null}
        <div
          className="absolute inset-0"
          style={{
            backgroundColor: `color-mix(in srgb, var(--background) ${Math.round(
              compiled.artLayer.wash * 100,
            )}%, transparent)`,
          }}
        />
        <div className="relative z-10 flex h-full min-h-0">
          <aside
            className="hidden sm:flex w-14 shrink-0 flex-col gap-2 border-r border-border/40 p-2"
            style={{ backgroundColor: `color-mix(in srgb, var(--background) ${Math.round(compiled.artLayer.navOpacity * 100)}%, transparent)` }}
          >
            <span className="h-2 w-8 rounded bg-primary/40" />
            <span className="h-2 w-6 rounded bg-muted-foreground/20" />
            <span className="h-2 w-7 rounded bg-muted-foreground/20" />
          </aside>
          <main
            className="flex min-w-0 flex-1 flex-col gap-2 p-3"
            style={{ backgroundColor: `color-mix(in srgb, var(--background) ${Math.round(compiled.artLayer.mainOpacity * 100)}%, transparent)` }}
          >
            {scene === 'chat' ? (
              <>
                <span className="mx-auto mt-6 h-3 w-24 rounded bg-muted-foreground/25" />
                <span className="mx-auto h-2 w-40 rounded bg-muted-foreground/15" />
                <span className="mt-auto h-8 rounded-lg border border-border/50 bg-background/70" />
              </>
            ) : null}
            {scene === 'kanban' ? (
              <div className="grid flex-1 grid-cols-3 gap-2">
                {[0, 1, 2].map((column) => (
                  <div key={column} className="rounded-lg border border-border/40 bg-background/60 p-2">
                    <span className="mb-2 block h-2 w-10 rounded bg-primary/30" />
                    <span className="mb-1 block h-8 rounded bg-muted/40" />
                    <span className="block h-8 rounded bg-muted/30" />
                  </div>
                ))}
              </div>
            ) : null}
            {scene === 'settings' || scene === 'workDense' ? (
              <div className="space-y-2">
                <span className="block h-3 w-20 rounded bg-primary/35" />
                <span className="block h-8 rounded-lg border border-border/40 bg-background/75" />
                <span className="block h-8 rounded-lg border border-border/40 bg-background/70" />
                <span className="block h-8 rounded-lg border border-border/40 bg-background/65" />
              </div>
            ) : null}
          </main>
        </div>
      </div>
    </div>
  );
};

export default ThemeStudioPreview;
