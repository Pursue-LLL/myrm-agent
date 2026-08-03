import type { ThemeLayoutId } from './schema';

/** Map hero media aspect ratio to a readable default layout (deterministic, no LLM). */
export function recommendLayoutFromAspect(aspectRatio: number): ThemeLayoutId {
  if (!Number.isFinite(aspectRatio) || aspectRatio <= 0) {
    return 'full-bleed';
  }
  if (aspectRatio >= 1.35) {
    return 'full-bleed';
  }
  if (aspectRatio <= 0.85) {
    return 'nav-rail-focus';
  }
  return 'chat-hero';
}
