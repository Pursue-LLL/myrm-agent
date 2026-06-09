/**
 * [INPUT]
 * - harness apply_approval_decisions extensions.allowAlways contract
 *
 * [OUTPUT]
 * - AllowAlwaysScope, AllowAlwaysValue, scopeToAllowAlwaysValue()
 *
 * [POS]
 * Single source for allow-always scope mapping across HITL surfaces.
 */

export type AllowAlwaysScope = 'permission' | 'tool' | 'exact';

export type AllowAlwaysValue = boolean | { tool?: boolean; args?: boolean };

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
  return { tool: true };
}
