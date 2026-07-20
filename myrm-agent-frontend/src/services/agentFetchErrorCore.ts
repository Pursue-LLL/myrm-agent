/**
 * [INPUT] agent.ts::listAgentSecrets, throwUserAgentFetchError (POS: /user-agents API client)
 * [OUTPUT] parseUserAgentFetchErrorMessage, normalizeAgentSecretKeyNames
 * [POS] Pure helpers for /user-agents fetch error parsing and secret list normalization.
 */

export interface AgentSecretKeyRef {
  key_name: string;
}

export function parseUserAgentFetchErrorMessage(
  errorText: string,
  action: string,
  statusText: string,
): string {
  let message = `Failed to ${action}: ${statusText}`;
  try {
    if (errorText) {
      const errorData = JSON.parse(errorText) as {
        detail?: { message?: string } | string;
        message?: string;
      };
      const detail = errorData.detail;
      if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
        message = detail.message;
      } else if (typeof detail === 'string') {
        message = detail;
      } else if (typeof errorData.message === 'string' && errorData.message) {
        message = errorData.message;
      }
    }
  } catch {
    // Keep default message when body is not JSON.
  }
  return message;
}

export function normalizeAgentSecretKeyNames(rows: unknown): string[] {
  if (!Array.isArray(rows)) {
    return [];
  }
  return rows.map((row, index) => {
    if (
      typeof row === 'object' &&
      row !== null &&
      'key_name' in row &&
      typeof (row as AgentSecretKeyRef).key_name === 'string'
    ) {
      return (row as AgentSecretKeyRef).key_name;
    }
    throw new Error(`Invalid agent secret list entry at index ${index}`);
  });
}
