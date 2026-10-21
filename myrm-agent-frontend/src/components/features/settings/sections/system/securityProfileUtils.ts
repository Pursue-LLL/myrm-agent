import type { PermissionAction } from '@/services/config/types';
import { flattenPermissions, deriveCapabilityMatrix } from './securityPolicyUtils';

export function parseProfileConfig(configJson: Record<string, unknown>) {
  const perms = configJson.permissions as
    Record<string, PermissionAction | Record<string, PermissionAction>> | undefined;
  const rawMatrix = configJson.capabilityMatrix as Record<string, PermissionAction> | undefined;
  const flattened = perms ? flattenPermissions(perms) : undefined;
  const derivedMatrix = flattened ? deriveCapabilityMatrix(rawMatrix, flattened) : undefined;

  const pp = configJson.pathPolicy as { allowedRoots?: string[] } | undefined;
  const roots = pp?.allowedRoots ?? [];

  return {
    rules: flattened,
    capabilityMatrix: rawMatrix,
    derivedMatrix,
    roots,
    timeout: configJson.approvalTimeoutSeconds as number | undefined,
    behavior: configJson.approvalTimeoutBehavior as 'deny' | 'allow' | undefined,
    domains: configJson.networkAllowlist as string[] | undefined,
    blockedDomains: configJson.networkBlocklist as string[] | undefined,
    cmdDenylist: configJson.commandDenylist as string[] | undefined,
    hitl: configJson.domainHitlEnabled as boolean | undefined,
    injection: configJson.injectionPolicy as 'log_only' | 'fail_closed' | undefined,
    planConfirm: configJson.planConfirmEnabled as boolean | undefined,
    yoloMode: configJson.yoloModeEnabled as boolean | undefined,
    autoReview: configJson.autoReviewEnabled as boolean | undefined,
  };
}

export function parseNLGeneratedConfig(generated: Record<string, unknown>) {
  const perms = generated.permissions as
    Record<string, PermissionAction | Record<string, PermissionAction>> | undefined;
  const newRules = perms ? flattenPermissions(perms) : undefined;
  const pp = generated.pathPolicy as { allowedRoots?: string[] } | undefined;

  return {
    rules: newRules,
    roots: pp?.allowedRoots,
    domains: generated.networkAllowlist as string[] | undefined,
    blockedDomains: generated.networkBlocklist as string[] | undefined,
    cmdDenylist: generated.commandDenylist as string[] | undefined,
    hitl: generated.domainHitlEnabled !== undefined ? Boolean(generated.domainHitlEnabled) : undefined,
    planConfirm: generated.planConfirmEnabled !== undefined ? Boolean(generated.planConfirmEnabled) : undefined,
  };
}
