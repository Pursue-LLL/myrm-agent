import { render, screen, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

let mockPathname = '/';

vi.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

// framer-motion 的 reduced-motion 语义无法在 jsdom 里靠计算样式断言，因此把它的根配置原样透出到
// data 属性，钉住「壳层确实用 reducedMotion="user" 包住两种应用内形态」这一契约。
vi.mock('framer-motion', () => ({
  MotionConfig: ({ reducedMotion, children }: { reducedMotion?: string; children: React.ReactNode }) => (
    <div data-testid="motion-config" data-reduced-motion={reducedMotion}>
      {children}
    </div>
  ),
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

vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isSandbox: vi.fn(() => false),
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

vi.mock('../../features/onboarding/OnboardingWizard', () => ({
  __esModule: true,
  default: ({ onComplete }: { onComplete: () => void }) => (
    <div data-testid="onboarding-wizard-mock">
      <button type="button" onClick={onComplete}>
        complete-onboarding
      </button>
    </div>
  ),
}));

import PageLayout from '../PageLayout';
import { shouldShowBootScreen } from '../../features/app-shell/boot-screen-gate';
import { isSandbox } from '@/lib/deploy-mode';
import { getReadinessStatus } from '@/services/onboarding';

const mockShouldShowBootScreen = vi.mocked(shouldShowBootScreen);

describe('PageLayout', () => {
  beforeEach(() => {
    mockPathname = '/';
    vi.clearAllMocks();
    vi.mocked(isSandbox).mockReturnValue(false);
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
      () =>
        new Promise(() => {
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

  describe('first-run onboarding', () => {
    const unfinished = {
      onboarding_completed: false,
      degraded: false,
      provider: { is_ready: false, missing_items: [], suggestions: [] },
      search: { is_ready: false },
    };

    it('runs the wizard for a hosted sandbox that has not finished onboarding', async () => {
      vi.mocked(isSandbox).mockReturnValue(true);
      vi.mocked(getReadinessStatus).mockResolvedValueOnce(unfinished);
      mockShouldShowBootScreen.mockReturnValue(true);
      render(
        <PageLayout>
          <span>child</span>
        </PageLayout>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('onboarding-wizard-mock')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('boot-screen-mock')).not.toBeInTheDocument();

      act(() => {
        screen.getByRole('button', { name: 'complete-onboarding' }).click();
      });
      await waitFor(() => {
        expect(screen.queryByTestId('onboarding-wizard-mock')).not.toBeInTheDocument();
      });
    });

    it('lets a local install straight in even though onboarding was never completed', async () => {
      vi.mocked(getReadinessStatus).mockResolvedValueOnce(unfinished);
      mockShouldShowBootScreen.mockReturnValue(false);
      render(
        <PageLayout>
          <span>child</span>
        </PageLayout>,
      );

      await waitFor(() => {
        expect(getReadinessStatus).toHaveBeenCalled();
      });
      expect(screen.getByTestId('app-layout')).toBeInTheDocument();
      expect(screen.queryByTestId('onboarding-wizard-mock')).not.toBeInTheDocument();
    });

    it('still plays the cold-start boot screen for a local install that never finished onboarding', async () => {
      vi.mocked(getReadinessStatus).mockResolvedValueOnce(unfinished);
      mockShouldShowBootScreen.mockReturnValue(true);
      render(
        <PageLayout>
          <span>child</span>
        </PageLayout>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('boot-screen-mock')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('onboarding-wizard-mock')).not.toBeInTheDocument();
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

  it('follows the OS reduced-motion setting for framer-motion, which CSS cannot reach', () => {
    mockShouldShowBootScreen.mockReturnValue(false);
    render(
      <PageLayout>
        <span>child</span>
      </PageLayout>,
    );

    expect(screen.getByTestId('motion-config')).toHaveAttribute('data-reduced-motion', 'user');
    // The wrapper must sit above the shell, otherwise a component rendered beside AppLayout escapes it.
    expect(screen.getByTestId('motion-config')).toContainElement(screen.getByTestId('app-layout'));
  });

  it('applies the same reduced-motion root to focused session windows, which skip AppLayout', () => {
    window.history.replaceState({}, '', '/chat-1?mode=focused');
    mockShouldShowBootScreen.mockReturnValue(false);
    render(
      <PageLayout>
        <span>focused-child</span>
      </PageLayout>,
    );

    expect(screen.getByTestId('motion-config')).toHaveAttribute('data-reduced-motion', 'user');
    expect(screen.getByTestId('motion-config')).toContainElement(screen.getByText('focused-child'));
    expect(screen.queryByTestId('app-layout')).not.toBeInTheDocument();
  });
});
