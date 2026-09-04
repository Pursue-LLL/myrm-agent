/**
 * [INPUT]
 * - harness apply_approval_decisions extensions.allowAlways contract
 *
 * [OUTPUT]
 * - AllowAlwaysScope, AllowAlwaysValue, scopeToAllowAlwaysValue(), defaultAllowAlwaysScope()
 *
 * [POS]
 * Single source for allow-always scope mapping across HITL surfaces.
 */

import { isShellApprovalTool } from '@/lib/approval/shellCommandDisplay';

export type AllowAlwaysScope = 'permission' | 'tool' | 'exact' | 'pattern';

export type AllowAlwaysDuration = 'session' | '15m' | '1h' | 'permanent';

export type AllowAlwaysValue =
  | boolean
  | {
      tool?: boolean;
      args?: boolean;
      pattern?: boolean;
      duration?: AllowAlwaysDuration;
      ttl_seconds?: number;
    };

/**
 * [INPUT] Duration option from confirm dialog
 * [OUTPUT] Seconds until expiry, or undefined for permanent, or -1 for session
 * [POS] Pure helper mapping duration enum to standard ttl seconds
 */
export function durationToTtlSeconds(duration: AllowAlwaysDuration): number | undefined {
  switch (duration) {
    case '15m':
      return 15 * 60;
    case '1h':
      return 60 * 60;
    case 'session':
      return -1;
    case 'permanent':
    default:
      return undefined;
  }
}

/**
 * [INPUT] User-selected allow-always scope and duration from confirm dialog
 * [OUTPUT] Harness-compatible allow_always extension value with ttl metadata
 * [POS] Shared mapping for SingleApprovalCard and PolymorphicApprovalCard
 */
export function scopeToAllowAlwaysValue(
  scope: AllowAlwaysScope,
  duration: AllowAlwaysDuration = 'session',
): AllowAlwaysValue {
  const ttl = durationToTtlSeconds(duration);
  const durationMeta = {
    duration,
    ...(ttl !== undefined && { ttl_seconds: ttl }),
  };

  if (scope === 'permission') {
    return duration === 'permanent' ? true : { tool: true, ...durationMeta };
  }
  if (scope === 'exact') {
    return { tool: true, args: true, ...durationMeta };
  }
  if (scope === 'pattern') {
    return { tool: true, pattern: true, ...durationMeta };
  }
  return { tool: true, ...durationMeta };
}

/** Default allow-always scope per tool — shell tools prefer exact match for safety. */
export function defaultAllowAlwaysScope(toolName: string): AllowAlwaysScope {
  if (isShellApprovalTool(toolName)) {
    return 'exact';
  }
  return 'tool';
}
