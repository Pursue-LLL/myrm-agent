/**
 * [INPUT] lib/fonts::FontId (POS: 全局字体 ID SSOT)
 * [INPUT] presets::getDefaultThemeProfile (POS: 内置主题 preset 默认值)
 * [OUTPUT] parseThemeRecipeJson: Skill/clipboard JSON → ThemeProfileRecipe patch
 * [OUTPUT] ThemeRecipeParseError: structured parse failures
 * [POS] Theme Recipe JSON 校验与规范化。供 Theme Studio 导入 AI 技能输出。
 */
import type { FontId } from '@/lib/fonts';
import { getDefaultThemeProfile } from './presets';
import { ART_WASH_MAX, ART_WASH_MIN } from './overlay';
import type { ThemeLayoutId, ThemeMediaKind, ThemePaletteTokens, ThemeProfileRecipe } from './schema';

const LAYOUT_IDS: ThemeLayoutId[] = ['full-bleed', 'nav-rail-focus', 'chat-hero', 'work-dense'];
const FONT_IDS: FontId[] = ['inter', 'system', 'atkinson'];
const MEDIA_KINDS: ThemeMediaKind[] = ['none', 'image', 'video'];

const HEX_PATTERN = /^#[0-9a-fA-F]{6}$/;

export type ThemeRecipeParseErrorCode =
  | 'invalid_json'
  | 'not_object'
  | 'missing_name'
  | 'invalid_layout'
  | 'invalid_font'
  | 'invalid_palette'
  | 'invalid_art';

export class ThemeRecipeParseError extends Error {
  readonly code: ThemeRecipeParseErrorCode;

  constructor(code: ThemeRecipeParseErrorCode, message: string) {
    super(message);
    this.name = 'ThemeRecipeParseError';
    this.code = code;
  }
}

function extractJsonPayload(raw: string): string {
  const trimmed = raw.trim();
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)```$/i);
  if (fenced) {
    return fenced[1].trim();
  }
  return trimmed;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined;
}

function readBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function readNumberInRange(value: unknown, min: number, max: number, fallback: number): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, value));
}

function readHexColor(value: unknown, field: string): string {
  const text = readString(value);
  if (!text || !HEX_PATTERN.test(text)) {
    throw new ThemeRecipeParseError('invalid_palette', `Invalid hex color for ${field}`);
  }
  return text.toLowerCase();
}

function parsePalette(raw: unknown, fallback: ThemePaletteTokens): ThemePaletteTokens {
  if (!isRecord(raw)) {
    throw new ThemeRecipeParseError('invalid_palette', 'palette must be an object');
  }
  return {
    primaryLight: readHexColor(raw.primaryLight ?? fallback.primaryLight, 'primaryLight'),
    primaryDark: readHexColor(raw.primaryDark ?? fallback.primaryDark, 'primaryDark'),
    primaryHoverLight: readHexColor(
      raw.primaryHoverLight ?? fallback.primaryHoverLight,
      'primaryHoverLight',
    ),
    primaryHoverDark: readHexColor(
      raw.primaryHoverDark ?? fallback.primaryHoverDark,
      'primaryHoverDark',
    ),
    primaryDarkLight: readHexColor(
      raw.primaryDarkLight ?? fallback.primaryDarkLight,
      'primaryDarkLight',
    ),
    primaryDarkDark: readHexColor(
      raw.primaryDarkDark ?? fallback.primaryDarkDark,
      'primaryDarkDark',
    ),
    dualAccent: readBoolean(raw.dualAccent, fallback.dualAccent),
    accentWarmLight: readString(raw.accentWarmLight) ?? fallback.accentWarmLight,
    accentWarmDark: readString(raw.accentWarmDark) ?? fallback.accentWarmDark,
  };
}

function parseArt(raw: unknown, fallback: ThemeProfileRecipe['art']): ThemeProfileRecipe['art'] {
  if (raw === undefined) {
    return { ...fallback };
  }
  if (!isRecord(raw)) {
    throw new ThemeRecipeParseError('invalid_art', 'art must be an object');
  }
  const mediaKindRaw = readString(raw.mediaKind) ?? fallback.mediaKind;
  if (!MEDIA_KINDS.includes(mediaKindRaw as ThemeMediaKind)) {
    throw new ThemeRecipeParseError('invalid_art', 'art.mediaKind must be image, video, or none');
  }
  const assetRef = readString(raw.assetRef) ?? fallback.assetRef ?? null;
  const posterAssetRef = readString(raw.posterAssetRef) ?? fallback.posterAssetRef ?? null;
  if (assetRef !== null && !assetRef.startsWith('file:')) {
    throw new ThemeRecipeParseError(
      'invalid_art',
      'art.assetRef must be null until media is uploaded in Theme Studio step 1',
    );
  }
  if (posterAssetRef !== null && !posterAssetRef.startsWith('file:')) {
    throw new ThemeRecipeParseError(
      'invalid_art',
      'art.posterAssetRef must be null until media is uploaded in Theme Studio step 1',
    );
  }
  return {
    focusX: readNumberInRange(raw.focusX, 0, 1, fallback.focusX),
    focusY: readNumberInRange(raw.focusY, 0, 1, fallback.focusY),
    wash: readNumberInRange(raw.wash, ART_WASH_MIN, ART_WASH_MAX, fallback.wash),
    mediaKind: mediaKindRaw as ThemeMediaKind,
    assetRef,
    posterAssetRef,
  };
}

/** Parse Skill or clipboard JSON into a studio draft patch (id/builtin ignored). */
export function parseThemeRecipeJson(raw: string): Partial<ThemeProfileRecipe> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(extractJsonPayload(raw));
  } catch {
    throw new ThemeRecipeParseError('invalid_json', 'Invalid JSON');
  }
  if (!isRecord(parsed)) {
    throw new ThemeRecipeParseError('not_object', 'Recipe must be a JSON object');
  }

  const fallback = getDefaultThemeProfile();
  const name = readString(parsed.name);
  if (!name) {
    throw new ThemeRecipeParseError('missing_name', 'name is required');
  }

  const layoutId = readString(parsed.layoutId);
  if (!layoutId || !LAYOUT_IDS.includes(layoutId as ThemeLayoutId)) {
    throw new ThemeRecipeParseError('invalid_layout', 'layoutId is invalid');
  }

  const fontId = readString(parsed.fontId);
  if (!fontId || !FONT_IDS.includes(fontId as FontId)) {
    throw new ThemeRecipeParseError('invalid_font', 'fontId is invalid');
  }

  return {
    name,
    layoutId: layoutId as ThemeLayoutId,
    fontId: fontId as FontId,
    palette: parsePalette(parsed.palette, fallback.palette),
    art: parseArt(parsed.art, fallback.art),
    packageDescription: readString(parsed.packageDescription) ?? null,
    packageTagline: readString(parsed.packageTagline) ?? null,
    packageAuthor: readString(parsed.packageAuthor) ?? null,
    packagePreviewAssetRef: readString(parsed.packagePreviewAssetRef) ?? null,
  };
}
