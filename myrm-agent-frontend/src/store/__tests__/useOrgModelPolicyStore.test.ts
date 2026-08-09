import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchOrgModelPolicy = vi.fn();

vi.mock('@/services/org-model-policy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/org-model-policy')>();
  return {
    ...actual,
    fetchOrgModelPolicy: (...args: unknown[]) => fetchOrgModelPolicy(...args),
  };
});

describe('useOrgModelPolicyStore', () => {
  beforeEach(() => {
    vi.resetModules();
    fetchOrgModelPolicy.mockReset();
  });

  it('dedupes concurrent loadPolicy calls', async () => {
    let resolveFetch: (value: { allowed_patterns: string[]; restricted: boolean }) => void = () => {};
    fetchOrgModelPolicy.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    );

    const { useOrgModelPolicyStore } = await import('@/store/useOrgModelPolicyStore');
    const first = useOrgModelPolicyStore.getState().loadPolicy();
    const second = useOrgModelPolicyStore.getState().loadPolicy();

    expect(fetchOrgModelPolicy).toHaveBeenCalledTimes(1);

    resolveFetch({ allowed_patterns: ['deepseek-*'], restricted: true });
    await Promise.all([first, second]);

    expect(useOrgModelPolicyStore.getState().patterns).toEqual(['deepseek-*']);
    expect(useOrgModelPolicyStore.getState().restricted).toBe(true);
  });

  it('refetches on subsequent loadPolicy after prior completion', async () => {
    fetchOrgModelPolicy
      .mockResolvedValueOnce({ allowed_patterns: ['gpt-*'], restricted: true })
      .mockResolvedValueOnce({ allowed_patterns: ['deepseek-*'], restricted: true });

    const { useOrgModelPolicyStore } = await import('@/store/useOrgModelPolicyStore');
    await useOrgModelPolicyStore.getState().loadPolicy();
    await useOrgModelPolicyStore.getState().loadPolicy();

    expect(fetchOrgModelPolicy).toHaveBeenCalledTimes(2);
    expect(useOrgModelPolicyStore.getState().patterns).toEqual(['deepseek-*']);
  });

  it('fail-closed when fetch throws in sandbox mode', async () => {
    vi.doMock('@/lib/deploy-mode', () => ({
      isSandbox: () => true,
    }));
    fetchOrgModelPolicy.mockRejectedValueOnce(new Error('network'));

    const { useOrgModelPolicyStore } = await import('@/store/useOrgModelPolicyStore');
    await useOrgModelPolicyStore.getState().loadPolicy();

    expect(useOrgModelPolicyStore.getState().patterns).toEqual([]);
    expect(useOrgModelPolicyStore.getState().restricted).toBe(true);
    expect(useOrgModelPolicyStore.getState().initialized).toBe(true);
    expect(useOrgModelPolicyStore.getState().isModelAllowed('openai/gpt-4o')).toBe(false);
    vi.doUnmock('@/lib/deploy-mode');
  });

  it('fail-open when fetch throws outside sandbox mode', async () => {
    vi.doMock('@/lib/deploy-mode', () => ({
      isSandbox: () => false,
    }));
    fetchOrgModelPolicy.mockRejectedValueOnce(new Error('network'));

    const { useOrgModelPolicyStore } = await import('@/store/useOrgModelPolicyStore');
    await useOrgModelPolicyStore.getState().loadPolicy();

    expect(useOrgModelPolicyStore.getState().patterns).toEqual([]);
    expect(useOrgModelPolicyStore.getState().restricted).toBe(false);
    vi.doUnmock('@/lib/deploy-mode');
  });
});
