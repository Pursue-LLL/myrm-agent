/**
 * Stable canonical fingerprint for config values.
 * Used to skip no-op syncs and detect real content changes.
 */

export function sortKeys(obj: unknown): unknown {
  if (obj === null || typeof obj !== 'object') {
    return obj;
  }
  if (Array.isArray(obj)) {
    return obj.map(sortKeys);
  }
  const sortedKeys = Object.keys(obj as Record<string, unknown>).sort();
  const result: Record<string, unknown> = {};
  for (const key of sortedKeys) {
    result[key] = sortKeys((obj as Record<string, unknown>)[key]);
  }
  return result;
}

export function fingerprintValue(value: unknown): string {
  return JSON.stringify(sortKeys(value));
}

export function valuesEqual(a: unknown, b: unknown): boolean {
  return fingerprintValue(a) === fingerprintValue(b);
}
