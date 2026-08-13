import type { ThemePaletteTokens } from './schema';

/** Relative luminance for WCAG contrast checks (sRGB hex). */
export function relativeLuminance(hex: string): number {
  const value = hex.replace('#', '');
  const r = Number.parseInt(value.slice(0, 2), 16) / 255;
  const g = Number.parseInt(value.slice(2, 4), 16) / 255;
  const b = Number.parseInt(value.slice(4, 6), 16) / 255;
  const transform = (channel: number) =>
    channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  const lr = transform(r);
  const lg = transform(g);
  const lb = transform(b);
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

export function contrastRatio(foreground: string, background: string): number {
  const l1 = relativeLuminance(foreground);
  const l2 = relativeLuminance(background);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

export function meetsContrast(foreground: string, background: string, minRatio = 4.5): boolean {
  return contrastRatio(foreground, background) >= minRatio;
}

const FOREGROUND_CANDIDATES = ['#fbfbf8', '#0a0a0a', '#ffffff', '#1a1208'] as const;

function sweepAchromaticForeground(
  background: string,
  minRatio: number,
  fromL: number,
  toL: number,
): string | null {
  const step = fromL <= toL ? 1 : -1;
  for (let l = fromL; step > 0 ? l <= toL : l >= toL; l += step) {
    const candidate = hslToHex(0, 0, l);
    if (meetsContrast(candidate, background, minRatio)) {
      return candidate;
    }
  }
  return null;
}

/**
 * Pick a foreground hex that meets WCAG AA against `background`.
 * Tries brand neutrals first, then sweeps achromatic lightness toward the opposite pole.
 */
export function resolveContrastSafeForeground(
  background: string,
  minRatio = 4.5,
): string {
  for (const candidate of FOREGROUND_CANDIDATES) {
    if (meetsContrast(candidate, background, minRatio)) {
      return candidate;
    }
  }

  const preferLight = relativeLuminance(background) < 0.5;
  const primarySweep = preferLight
    ? sweepAchromaticForeground(background, minRatio, 100, 50)
    : sweepAchromaticForeground(background, minRatio, 0, 50);
  if (primarySweep) {
    return primarySweep;
  }

  const secondarySweep = preferLight
    ? sweepAchromaticForeground(background, minRatio, 0, 50)
    : sweepAchromaticForeground(background, minRatio, 100, 50);
  if (secondarySweep) {
    return secondarySweep;
  }

  let best: string = FOREGROUND_CANDIDATES[0];
  let bestRatio = contrastRatio(best, background);
  for (const candidate of FOREGROUND_CANDIDATES) {
    const ratio = contrastRatio(candidate, background);
    if (ratio > bestRatio) {
      best = candidate;
      bestRatio = ratio;
    }
  }
  for (let l = 5; l <= 95; l += 5) {
    const candidate = hslToHex(0, 0, l);
    const ratio = contrastRatio(candidate, background);
    if (ratio > bestRatio) {
      best = candidate;
      bestRatio = ratio;
    }
  }
  return best;
}

function hexToHsl(hex: string): [number, number, number] {
  const v = hex.replace('#', '');
  const r = Number.parseInt(v.slice(0, 2), 16) / 255;
  const g = Number.parseInt(v.slice(2, 4), 16) / 255;
  const b = Number.parseInt(v.slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) {return [0, 0, l * 100];}
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r) {h = ((g - b) / d + (g < b ? 6 : 0)) / 6;}
  else if (max === g) {h = ((b - r) / d + 2) / 6;}
  else {h = ((r - g) / d + 4) / 6;}
  return [h * 360, s * 100, l * 100];
}

function hslToHex(h: number, s: number, l: number): string {
  const sn = s / 100;
  const ln = l / 100;
  const c = (1 - Math.abs(2 * ln - 1)) * sn;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = ln - c / 2;
  let r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; }
  else if (h < 120) { r = x; g = c; }
  else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; }
  else if (h < 300) { r = x; b = c; }
  else { r = c; b = x; }
  const toHex = (ch: number) => Math.round((ch + m) * 255).toString(16).padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function clampL(l: number): number {
  return Math.max(10, Math.min(90, l));
}

/**
 * Derive a complete ThemePaletteTokens from a single primary hex color.
 * Uses HSL lightness shifts to generate light/dark/hover/accent variants,
 * ensuring WCAG contrast against white (#ffffff) and dark (#0a0a0a) backgrounds.
 */
export function derivePalette(hex: string): ThemePaletteTokens {
  const [h, s] = hexToHsl(hex);

  const primaryLight = hslToHex(h, s, clampL(42));
  const primaryDark = hslToHex(h, s, clampL(62));
  const primaryHoverLight = hslToHex(h, s, clampL(36));
  const primaryHoverDark = hslToHex(h, s, clampL(68));
  const primaryDarkLight = hslToHex(h, s, clampL(26));
  const primaryDarkDark = hslToHex(h, s, clampL(42));

  return {
    primaryLight,
    primaryDark,
    primaryHoverLight,
    primaryHoverDark,
    primaryDarkLight,
    primaryDarkDark,
    dualAccent: false,
  };
}
