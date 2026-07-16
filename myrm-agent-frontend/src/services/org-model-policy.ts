/**
 * Organization Model Policy API client.
 *
 * Fetches org-level model whitelist patterns from the server.
 * Used by frontend to grey-out/hide restricted models.
 */

import { getApiUrl } from '@/lib/api';

export interface OrgModelPolicyResponse {
  allowed_patterns: string[];
  restricted: boolean;
}

export async function fetchOrgModelPolicy(): Promise<OrgModelPolicyResponse> {
  const url = getApiUrl('/api/org-policy/allowed-models');
  const res = await fetch(url);
  if (!res.ok) {
    return { allowed_patterns: [], restricted: false };
  }
  return res.json();
}

/**
 * Check if a model name matches any of the allowed glob patterns.
 * Uses minimatch-style glob: * matches any chars within a segment.
 */
export function isModelAllowedByPolicy(modelName: string, patterns: string[]): boolean {
  if (patterns.length === 0) return true;
  return patterns.some((pattern) => globMatch(modelName, pattern));
}

function globMatch(str: string, pattern: string): boolean {
  const regex = new RegExp(
    '^' + pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$',
  );
  return regex.test(str);
}
