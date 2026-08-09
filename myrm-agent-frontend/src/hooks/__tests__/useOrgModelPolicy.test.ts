import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const fetchOrgModelPolicy = vi.fn();

const deployModeMocks = vi.hoisted(() => ({
  isSandbox: vi.fn(() => false),
}));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isSandbox: () => deployModeMocks.isSandbox(),
  };
});

vi.mock('@/services/org-model-policy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/org-model-policy')>();
  return {
    ...actual,
    fetchOrgModelPolicy: (...args: unknown[]) => fetchOrgModelPolicy(...args),
  };
});

vi.mock('@/hooks/useOrgModelPolicySync', () => ({
  useOrgModelPolicySync: vi.fn(),
}));

describe('useOrgModelPolicy', () => {
  beforeEach(() => {
    vi.resetModules();
    fetchOrgModelPolicy.mockReset();
    deployModeMocks.isSandbox.mockReturnValue(false);
  });

  async function loadHook() {
    const { useOrgModelPolicy } = await import('@/hooks/useOrgModelPolicy');
    return renderHook(() => useOrgModelPolicy());
  }

  it('delegates isModelAllowed to store fail-closed sentinel in sandbox', async () => {
    deployModeMocks.isSandbox.mockReturnValue(true);
    fetchOrgModelPolicy.mockRejectedValueOnce(new Error('network'));

    const { result } = await loadHook();

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.restricted).toBe(true);
    expect(result.current.isModelAllowed('openai/gpt-4o')).toBe(false);
  });

  it('delegates isModelAllowed to store whitelist patterns', async () => {
    fetchOrgModelPolicy.mockResolvedValueOnce({
      allowed_patterns: ['openai/*'],
      restricted: true,
    });

    const { result } = await loadHook();

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.isModelAllowed('openai/gpt-4o')).toBe(true);
    expect(result.current.isModelAllowed('anthropic/claude-3-5-sonnet')).toBe(false);
  });
});
