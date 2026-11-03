import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import FirstRunDoctorCard from '../FirstRunDoctorCard';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCheck: () => <span data-testid="icon-ok" />,
  IconAlertCircle: () => <span data-testid="icon-fail" />,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/lib/backend-health', () => ({
  checkBackendReadyOnce: vi.fn(() => Promise.resolve(mockBackendOk.value)),
}));

const mockFetchEntitlements = vi.hoisted(() => vi.fn());
vi.mock('@/lib/cp-billing', () => ({
  fetchEntitlements: mockFetchEntitlements,
}));

const mockProviders = vi.hoisted(() => ({
  value: [{ id: 'openai', isEnabled: true, apiKeys: [{ isActive: true, key: 'sk-x' }] }] as unknown[],
}));
const mockBackendOk = vi.hoisted(() => ({ value: true }));

vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ providers: mockProviders.value, isInitialized: true }),
}));

vi.mock('@/store/config/providerTypes', () => ({
  hasUsableProviderAuth: () => mockProviders.value.length > 0,
}));

describe('FirstRunDoctorCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProviders.value = [{ id: 'openai', isEnabled: true, apiKeys: [{ isActive: true, key: 'sk-x' }] }] as unknown[];
    mockBackendOk.value = true;
    mockFetchEntitlements.mockResolvedValue({ balance_wu: 10, subscription_wu: 0 });
    window.localStorage.clear();
  });

  it('shows all-clear when provider, backend and quota pass', async () => {
    render(<FirstRunDoctorCard />);
    await waitFor(() => {
      expect(screen.getByText('allClear')).toBeTruthy();
    });
    expect(screen.queryByText('fix')).toBeNull();
  });

  it('probes the quota with the signed-in token and flags an empty balance', async () => {
    window.localStorage.setItem('auth_token', 'tok');
    mockFetchEntitlements.mockResolvedValue({ balance_wu: 0, subscription_wu: 0 });
    render(<FirstRunDoctorCard />);
    await waitFor(() => {
      expect(screen.getByText('hasIssues')).toBeTruthy();
    });
    expect(mockFetchEntitlements).toHaveBeenCalledWith('tok');
    expect(screen.getAllByText('fix')).toHaveLength(1);
  });

  it('passes the quota row without probing when no one is signed in', async () => {
    render(<FirstRunDoctorCard />);
    await waitFor(() => {
      expect(screen.getByText('allClear')).toBeTruthy();
    });
    expect(mockFetchEntitlements).not.toHaveBeenCalled();
  });

  it('flags the quota row when the entitlements lookup fails', async () => {
    window.localStorage.setItem('auth_token', 'tok');
    mockFetchEntitlements.mockRejectedValue(new Error('offline'));
    render(<FirstRunDoctorCard />);
    await waitFor(() => {
      expect(screen.getByText('hasIssues')).toBeTruthy();
    });
    expect(screen.getAllByText('fix')).toHaveLength(1);
  });

  it('shows fix actions when nothing is ready', async () => {
    mockProviders.value = [];
    mockBackendOk.value = false;
    render(<FirstRunDoctorCard />);
    await waitFor(() => {
      expect(screen.getAllByText('fix').length).toBeGreaterThan(0);
    });
  });
});
