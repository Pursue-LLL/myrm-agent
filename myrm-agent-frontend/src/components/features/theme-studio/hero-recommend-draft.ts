import { derivePalette, type HeroImageSample, type ThemeProfileRecipe } from '@/theme-engine';

/**
 * [INPUT]
 * - HeroImageSample, ThemeProfileRecipe patch from Theme Studio wizard
 *
 * [OUTPUT]
 * - shouldClearHeroSampleOnDraftPatch, buildHeroSampleApplyPatch
 *
 * [POS]
 * Pure helpers keeping hero recommendation banner consistent with wizard draft edits.
 */

export function shouldClearHeroSampleOnDraftPatch(patch: Partial<ThemeProfileRecipe>): boolean {
  return 'palette' in patch || 'layoutId' in patch;
}

/** Apply recommendation: palette + layout only (focal is set on upload). */
export function buildHeroSampleApplyPatch(
  heroSample: HeroImageSample,
): Pick<ThemeProfileRecipe, 'layoutId' | 'palette'> {
  return {
    layoutId: heroSample.recommendedLayoutId,
    palette: derivePalette(heroSample.primaryHex),
  };
}
