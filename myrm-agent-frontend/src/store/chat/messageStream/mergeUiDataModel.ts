/**
 * Merge incremental UI data model updates into existing artifact data.
 *
 * Plain objects are merged recursively; arrays and scalars replace by key.
 */

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function mergeUiDataModel(
  current: Record<string, unknown>,
  updates: Record<string, unknown>,
): Record<string, unknown> {
  const result = structuredClone(current);

  for (const [key, value] of Object.entries(updates)) {
    const existing = result[key];
    if (isPlainObject(existing) && isPlainObject(value)) {
      result[key] = mergeUiDataModel(existing, value);
      continue;
    }
    result[key] = structuredClone(value);
  }

  return result;
}
