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

export type AllowAlwaysValue =
  | boolean
  | { tool?: boolean; args?: boolean; pattern?: boolean };

/**
 * [INPUT] User-selected allow-always scope from confirm dialog
 * [OUTPUT] Harness-compatible allow_always extension value
 * [POS] Shared mapping for SingleApprovalCard and PolymorphicApprovalCard
 */
export function scopeToAllowAlwaysValue(scope: AllowAlwaysScope): AllowAlwaysValue {
  if (scope === 'permission') {
    return true;
  }
  if (scope === 'exact') {
    return { tool: true, args: true };
  }
  if (scope === 'pattern') {
    return { tool: true, pattern: true };
  }
  return { tool: true };
}

/** Default allow-always scope per tool — shell tools prefer exact match for safety. */
export function defaultAllowAlwaysScope(toolName: string): AllowAlwaysScope {
  if (isShellApprovalTool(toolName)) {
    return 'exact';
  }
  return 'tool';
}
