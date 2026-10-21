import { describe, it, expect } from 'vitest';
import { resolveProviderDataUsage } from '../providerDataUsageCatalog';

describe('providerDataUsageCatalog', () => {
  it('returns self_hosted for local providers', () => {
    expect(resolveProviderDataUsage('ollama', true).policyKey).toBe('self_hosted');
  });

  it('returns catalog entry for known cloud providers', () => {
    const entry = resolveProviderDataUsage('openai', false);
    expect(entry.policyKey).toBe('api_not_used_for_training');
    expect(entry.docUrl).toContain('openai.com');
  });

  it('falls back to review_provider_policy for unknown providers', () => {
    expect(resolveProviderDataUsage('custom-provider', false).policyKey).toBe('review_provider_policy');
  });
});
