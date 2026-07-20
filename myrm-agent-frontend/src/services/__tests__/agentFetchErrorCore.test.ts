import { describe, expect, it } from 'vitest';
import {
  normalizeAgentSecretKeyNames,
  parseUserAgentFetchErrorMessage,
} from '../agentFetchErrorCore';

describe('parseUserAgentFetchErrorMessage', () => {
  it('uses detail.message from StandardHTTPException body', () => {
    const body = JSON.stringify({
      detail: { success: false, code: 1001, message: 'Key name and secret value are required' },
    });
    expect(parseUserAgentFetchErrorMessage(body, 'save agent secret', 'Bad Request')).toBe(
      'Key name and secret value are required',
    );
  });

  it('uses detail string for legacy HTTPException bodies', () => {
    const body = JSON.stringify({ detail: 'Vault is locked.' });
    expect(parseUserAgentFetchErrorMessage(body, 'list agent secrets', 'Locked')).toBe('Vault is locked.');
  });

  it('uses top-level message from MyrmError JSONResponse bodies', () => {
    const body = JSON.stringify({
      success: false,
      code: 5001,
      message: 'Create agent secret failed: storage unavailable',
    });
    expect(parseUserAgentFetchErrorMessage(body, 'save agent secret', 'Internal Server Error')).toBe(
      'Create agent secret failed: storage unavailable',
    );
  });

  it('falls back to statusText when body is not JSON', () => {
    expect(parseUserAgentFetchErrorMessage('not json', 'export agent', 'Forbidden')).toBe(
      'Failed to export agent: Forbidden',
    );
  });
});

describe('normalizeAgentSecretKeyNames', () => {
  it('maps key_name objects to string array for Secrets tab', () => {
    expect(
      normalizeAgentSecretKeyNames([{ key_name: 'SHOPIFY_API_KEY' }, { key_name: 'GITHUB_TOKEN' }]),
    ).toEqual(['SHOPIFY_API_KEY', 'GITHUB_TOKEN']);
  });

  it('returns empty array when payload is missing or not an array', () => {
    expect(normalizeAgentSecretKeyNames(undefined)).toEqual([]);
    expect(normalizeAgentSecretKeyNames(null)).toEqual([]);
    expect(normalizeAgentSecretKeyNames({})).toEqual([]);
  });

  it('throws when an entry is not a key_name object', () => {
    expect(() => normalizeAgentSecretKeyNames([{ key_name: 'OK' }, 'bad'])).toThrow(
      'Invalid agent secret list entry at index 1',
    );
  });
});
