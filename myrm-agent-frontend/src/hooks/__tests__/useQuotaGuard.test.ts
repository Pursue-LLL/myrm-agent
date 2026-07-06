import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

const toastError = vi.fn();

vi.mock('@/lib/cp-billing', () => ({
  fetchWorkUnitEstimate: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    info: vi.fn(),
  },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/store/useAuthStore', () => ({
  default: () => ({ token: null }),
}));

describe('useQuotaGuard', () => {
  const previousDeployMode = process.env.NEXT_PUBLIC_DEPLOY_MODE;

  afterEach(() => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = previousDeployMode;
  });

  it('shows toast when sandbox auth token is missing', async () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    vi.stubGlobal('localStorage', {
      getItem: () => null,
    });

    const { useQuotaGuard } = await import('@/hooks/useQuotaGuard');
    const { result } = renderHook(() => useQuotaGuard());

    const quota = await result.current.validateMessageQuota(10, false, 'agent');

    expect(quota.allowed).toBe(false);
    expect(quota.reason).toBe('wu_limit');
    expect(toastError).toHaveBeenCalledWith('insufficientWu');
  });
});
