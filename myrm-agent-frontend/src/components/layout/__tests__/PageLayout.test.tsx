import { render, screen, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

let mockPathname = '/';

vi.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

vi.mock('../AppLayout', () => ({
  __esModule: true,
  default: ({
    children,
    configReadinessDegraded,
  }: {
    children: React.ReactNode;
    configReadinessDegraded?: boolean;
  }) => (
    <div data-testid="app-layout" data-readiness-degraded={configReadinessDegraded ? '1' : '0'}>
      {children}
    </div>
  ),
}));

vi.mock('@/services/onboarding', () => ({
  getReadinessStatus: vi.fn(() =>
    Promise.resolve({
      onboarding_completed: true,
      degraded: false,
      provider: { is_ready: true, missing_items: [], suggestions: [] },
      search: { is_ready: true },
    }),
  ),
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(() => Promise.resolve(true)),
}));

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: vi.fn(() => false),
}));

vi.mock('../../features/app-shell/boot-screen-gate', () => ({
  shouldShowBootScreen: vi.fn(),
}));

vi.mock('../../features/app-shell/boot-screen', () => ({
  __esModule: true,
  default: ({ onComplete }: { onComplete: () => void }) => (
    <div data-testid="boot-screen-mock">
      <button type="button" onClick={onComplete}>
        complete-boot
      </button>
    </div>
  ),
}));

import PageLayout from '../PageLayout';
import { shouldShowBootScreen } from '../../features/app-shell/boot-screen-gate';

const mockShouldShowBootScreen = vi.mocked(shouldShowBootScreen);

describe('PageLayout', () => {
  beforeEach(() => {
    mockPathname = '/';
    vi.clearAllMocks();
  });

  it('enters AppLayout on first render without waiting for readiness', () => {
    mockShouldShowBootScreen.mockReturnValue(false);
    render(
      <PageLayout>
        <span>child</span>
      </PageLayout>,
    );

    expect(screen.getByTestId('app-layout')).toBeInTheDocument();
  });

  it('shows BootScreen on cold start and transitions to AppLayout', async () => {
    mockShouldShowBootScreen.mockReturnValue(true);
    render(
      <PageLayout>
        <span>child</span>
      </PageLayout>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('boot-screen-mock')).toBeInTheDocument();
    });

    act(() => {
      screen.getByRole('button', { name: 'complete-boot' }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('app-layout')).toBeInTheDocument();
      expect(screen.getByText('child')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('boot-screen-mock')).not.toBeInTheDocument();
  });

  it('skips BootScreen when session already marked', async () => {
    mockShouldShowBootScreen.mockReturnValue(false);
    render(
      <PageLayout>
        <span>child</span>
      </PageLayout>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('app-layout')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('boot-screen-mock')).not.toBeInTheDocument();
  });

  it('renders AppLayout immediately while readiness is still pending', async () => {
    const { getReadinessStatus } = await import('@/services/onboarding');
    vi.mocked(getReadinessStatus).mockImplementation(
      () => new Promise(() => {
        /* never resolves */
      }),
    );
    mockShouldShowBootScreen.mockReturnValue(true);

    render(
      <PageLayout>
        <span>child</span>
      </PageLayout>,
    );

    await waitFor(
      () => {
        expect(screen.getByTestId('app-layout')).toBeInTheDocument();
      },
      { timeout: 1_000 },
    );
    expect(screen.queryByTestId('boot-screen-mock')).not.toBeInTheDocument();
  });

  it('passes degraded readiness to AppLayout', async () => {
    const { getReadinessStatus } = await import('@/services/onboarding');
    vi.mocked(getReadinessStatus).mockResolvedValue({
      onboarding_completed: true,
      degraded: true,
      provider: { is_ready: false, missing_items: ['config_load_timeout'], suggestions: [] },
      search: { is_ready: false, missing_items: ['config_load_timeout'], suggestions: [] },
    });
    mockShouldShowBootScreen.mockReturnValue(false);

    render(
      <PageLayout>
        <span>child</span>
      </PageLayout>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('app-layout')).toHaveAttribute('data-readiness-degraded', '1');
    });
  });

  it('renders standalone routes without AppLayout or boot screen', () => {
    mockPathname = '/pricing';
    mockShouldShowBootScreen.mockReturnValue(true);
    render(
      <PageLayout>
        <span>pricing-child</span>
      </PageLayout>,
    );
    expect(screen.getByText('pricing-child')).toBeInTheDocument();
    expect(screen.queryByTestId('app-layout')).not.toBeInTheDocument();
    expect(screen.queryByTestId('boot-screen-mock')).not.toBeInTheDocument();
  });
});
