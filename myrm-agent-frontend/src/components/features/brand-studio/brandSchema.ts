/**
 * Brand style schema — pure, framework-agnostic definitions.
 *
 * Brand identity is stored as `brand_*` profile memories so it flows into the
 * agent's stable context layer as a "Global User Profile" (see harness
 * memory_context_format). This module owns the key mapping, validation, and
 * preview helpers. No I/O — kept separate for unit testing.
 */

export const BRAND_KEY_PREFIX = 'brand_';

/** Brand field key (profile memory key, excluding the `brand_` prefix). */
export type BrandFieldKey =
  | 'name'
  | 'tagline'
  | 'primary_color'
  | 'secondary_color'
  | 'accent_color'
  | 'font'
  | 'tone'
  | 'taboos';

/** Raw, order-stable list of brand fields (drives the form). */
export const BRAND_FIELD_KEYS: readonly BrandFieldKey[] = [
  'name',
  'tagline',
  'primary_color',
  'secondary_color',
  'accent_color',
  'font',
  'tone',
  'taboos',
];

export const isColorField = (key: BrandFieldKey): boolean =>
  key === 'primary_color' || key === 'secondary_color' || key === 'accent_color';

export const isLongTextField = (key: BrandFieldKey): boolean =>
  key === 'tagline' || key === 'taboos';

/** Profile memory key for a brand field. */
export const brandProfileKey = (key: BrandFieldKey): string => `${BRAND_KEY_PREFIX}${key}`;

/** Field key from a profile memory key (returns null if not a brand key). */
export const brandFieldFromProfileKey = (profileKey: string): BrandFieldKey | null => {
  if (!profileKey.startsWith(BRAND_KEY_PREFIX)) {return null;}
  const field = profileKey.slice(BRAND_KEY_PREFIX.length) as BrandFieldKey;
  return BRAND_FIELD_KEYS.includes(field) ? field : null;
};

/** Ordered map of resolved brand values (only set fields included). */
export type BrandValues = Partial<Record<BrandFieldKey, string>>;

/** Extract a BrandValues map from a list of profile memories. */
export function extractBrandValues(
  memories: ReadonlyArray<{ key?: string | null; value?: string | null }>,
): BrandValues {
  const values: BrandValues = {};
  for (const memory of memories) {
    const key = memory.key;
    const value = memory.value;
    if (!key) {continue;}
    const field = brandFieldFromProfileKey(key);
    if (field === null) {continue;}
    const trimmed = (value ?? '').trim();
    if (trimmed) {values[field] = trimmed;}
  }
  return values;
}

const HEX_COLOR_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export interface BrandFieldError {
  field: BrandFieldKey;
  message: string;
}

/**
 * Validate a single brand field value. Returns an error message or null.
 * Color fields require a valid hex; text fields require non-empty value.
 */
export function validateBrandField(field: BrandFieldKey, value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {return 'required';}
  if (isColorField(field) && !HEX_COLOR_RE.test(trimmed)) {
    return 'invalidHex';
  }
  return null;
}

/** Whether a profile key is a brand key (used to filter list responses). */
export function isBrandProfileKey(key: string | undefined | null): boolean {
  return !!key && key.startsWith(BRAND_KEY_PREFIX);
}

/** A brand entry as shown in the list UI. */
export interface BrandEntry {
  field: BrandFieldKey;
  key: string;
  value: string;
}

/** Build display entries from raw profile memories, ordered by BRAND_FIELD_KEYS. */
export function toBrandEntries(
  memories: ReadonlyArray<{ key?: string | null; value?: string | null }>,
): BrandEntry[] {
  const byField = extractBrandValues(memories);
  return BRAND_FIELD_KEYS.filter((field) => byField[field] !== undefined).map((field) => ({
    field,
    key: brandProfileKey(field),
    value: byField[field] as string,
  }));
}
