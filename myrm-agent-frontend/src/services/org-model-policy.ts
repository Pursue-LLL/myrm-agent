/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * - fetchOrgModelPolicy: Loads org model policy from backend
 * - isModelAllowedByPolicy: Checks if a model name matches allowed glob patterns
 *
 * [POS]
 * Frontend client for organization model policy. Provides glob-pattern matching
 * to filter model selections in cloud-hosted deployments.
 */

import { apiRequest } from '@/lib/api';

export interface OrgModelPolicyResponse {
  allowed_patterns: string[];
  restricted: boolean;
}

export async function fetchOrgModelPolicy(): Promise<OrgModelPolicyResponse> {
  return apiRequest<OrgModelPolicyResponse>('/org-policy/allowed-models');
}

function globToRegex(pattern: string): RegExp {
  const escaped = pattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '.*')
    .replace(/\?/g, '.');
  return new RegExp(`^${escaped}$`);
}

export function isModelAllowedByPolicy(modelName: string, patterns: string[]): boolean {
  if (patterns.length === 0) {
    return true;
  }
  return patterns.some((pattern) => globToRegex(pattern).test(modelName));
}
