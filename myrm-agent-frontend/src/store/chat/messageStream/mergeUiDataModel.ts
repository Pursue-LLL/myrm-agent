/**
 * Merge incremental UI data model updates into existing artifact data.
 *
 * Plain objects are merged recursively; arrays and scalars replace by key.
 */

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function cloneDataValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(cloneDataValue);
  }
  if (isPlainObject(value)) {
    const clone: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value)) {
      clone[key] = cloneDataValue(nested);
    }
    return clone;
  }
  // SSE data is normally JSON, but a malformed/locally enriched artifact can
  // contain a Window, function, or other host object that structuredClone
  // rejects. Preserve such values without mutating the containing data model.
  return value;
}

export function mergeUiDataModel(
  current: Record<string, unknown>,
  updates: Record<string, unknown>,
): Record<string, unknown> {
  const result = cloneDataValue(current) as Record<string, unknown>;

  for (const [key, value] of Object.entries(updates)) {
    const existing = result[key];
    if (isPlainObject(existing) && isPlainObject(value)) {
      result[key] = mergeUiDataModel(existing, value);
      continue;
    }
    result[key] = cloneDataValue(value);
  }

  return result;
}
