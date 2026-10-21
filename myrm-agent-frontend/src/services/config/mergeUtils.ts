import { cloneDeep, isEqual, isPlainObject } from 'lodash-es';

export interface MergeResult<T> {
  merged: T;
  hasConflict: boolean;
}

/**
 * 执行三向深度合并 (3-Way Deep Merge)
 *
 * @param base 基础版本（修改前的原始状态）
 * @param local 本地修改后的版本
 * @param server 服务端最新版本
 * @returns 合并结果及是否发生同字段冲突
 */
export function threeWayMerge(
  base: Record<string, unknown> | null | undefined,
  local: Record<string, unknown>,
  server: Record<string, unknown>,
): MergeResult<Record<string, unknown>> {
  if (!base) {
    const merged = cloneDeep(local) as Record<string, unknown>;
    let hasConflict = false;

    for (const key of Object.keys(server)) {
      if (!(key in local)) {
        merged[key] = cloneDeep(server[key]);
        continue;
      }
      if (!isEqual(local[key], server[key])) {
        hasConflict = true;
      }
    }

    return { merged, hasConflict };
  }

  const merged = cloneDeep(local) as Record<string, unknown>;
  let hasConflict = false;

  const allKeys = new Set([...Object.keys(base), ...Object.keys(local), ...Object.keys(server)]);

  for (const key of allKeys) {
    const baseVal = base[key];
    const localVal = local[key];
    const serverVal = server[key];

    if (isEqual(baseVal, serverVal)) {
      continue;
    }

    if (isEqual(baseVal, localVal)) {
      if (serverVal === undefined) {
        delete merged[key];
      } else {
        merged[key] = cloneDeep(serverVal);
      }
      continue;
    }

    if (isEqual(localVal, serverVal)) {
      if (serverVal === undefined) {
        delete merged[key];
      } else {
        merged[key] = cloneDeep(serverVal);
      }
      continue;
    }

    if (isPlainObject(baseVal) && isPlainObject(localVal) && isPlainObject(serverVal)) {
      const subMerge = threeWayMerge(
        baseVal as Record<string, unknown>,
        localVal as Record<string, unknown>,
        serverVal as Record<string, unknown>,
      );
      merged[key] = subMerge.merged;
      if (subMerge.hasConflict) {
        hasConflict = true;
      }
    } else {
      hasConflict = true;
    }
  }

  return { merged, hasConflict };
}
