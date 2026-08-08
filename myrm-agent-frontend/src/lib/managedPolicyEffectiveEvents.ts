/**
 * [INPUT]
 * - (none — constants only)
 *
 * [OUTPUT]
 * - MANAGED_POLICY_UPDATED_EVENT: window CustomEvent 名 SSOT
 * - ManagedPolicyUpdatedDetail: SSE payload detail 类型
 *
 * [POS]
 * Org MAP SSE push → 浏览器内 CustomEvent 桥接常量。供 useGlobalEvents 派发、hook subscribe。
 */

export const MANAGED_POLICY_UPDATED_EVENT = 'managed-policy-updated';

export interface ManagedPolicyUpdatedDetail {
  revision?: number;
  active?: boolean;
}
