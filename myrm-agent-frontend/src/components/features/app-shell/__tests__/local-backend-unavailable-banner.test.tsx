import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LocalBackendUnavailableBanner, {
  dismissLocalBackendBanner,
  isLocalBackendBannerDismissed,
} from '../local-backend-unavailable-banner';

vi.mock('@/lib/backend-health', () => ({
  checkBackendReadyOnce: vi.fn(() => Promise.resolve(true)),
  fetchBackendHealth: vi.fn(() => Promise.resolve(null)),
}));

vi.mock('@/lib/local-backend-dev', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/local-backend-dev')>();
  return {
    ...actual,
    resolveLocalBackendSetupHint: vi.fn(() => Promise.resolve('hintUnreachable')),
  };
});

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: vi.fn(() => true),
}));

describe('isLocalBackendBannerDismissed', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('returns false when sessionStorage has no dismiss key', () => {
    expect(isLocalBackendBannerDismissed()).toBe(false);
  });

  it('returns true after dismissLocalBackendBanner', () => {
    dismissLocalBackendBanner();
    expect(isLocalBackendBannerDismissed()).toBe(true);
  });
});

describe('LocalBackendUnavailableBanner', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.clearAllMocks();
  });

  it('shows banner when local backend health check fails', async () => {
    const { checkBackendReadyOnce } = await import('@/lib/backend-health');
    vi.mocked(checkBackendReadyOnce).mockResolvedValueOnce(false);

    render(<LocalBackendUnavailableBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('local-backend-unavailable-banner')).toHaveTextContent('hintUnreachable');
  });

  it('does not show banner when backend is ready', async () => {
    const { checkBackendReadyOnce } = await import('@/lib/backend-health');
    vi.mocked(checkBackendReadyOnce).mockResolvedValueOnce(true);

    render(<LocalBackendUnavailableBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByTestId('local-backend-unavailable-banner')).not.toBeInTheDocument();
  });

  it('does not show banner outside local mode', async () => {
    const { isLocalMode } = await import('@/lib/deploy-mode');
    const { checkBackendReadyOnce } = await import('@/lib/backend-health');
    vi.mocked(isLocalMode).mockReturnValueOnce(false);
    vi.mocked(checkBackendReadyOnce).mockResolvedValueOnce(false);

    render(<LocalBackendUnavailableBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByTestId('local-backend-unavailable-banner')).not.toBeInTheDocument();
    expect(checkBackendReadyOnce).not.toHaveBeenCalled();
  });

  it('hides banner when dismissed and persists for the session', async () => {
    const { checkBackendReadyOnce } = await import('@/lib/backend-health');
    vi.mocked(checkBackendReadyOnce).mockResolvedValueOnce(false);

    render(<LocalBackendUnavailableBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    const dismissButton = screen.getByRole('button', { name: 'close' });
    fireEvent.click(dismissButton);

    expect(screen.queryByTestId('local-backend-unavailable-banner')).not.toBeInTheDocument();
    expect(isLocalBackendBannerDismissed()).toBe(true);
  });

  it('does not show banner when previously dismissed in session', async () => {
    dismissLocalBackendBanner();
    const { checkBackendReadyOnce } = await import('@/lib/backend-health');

    render(<LocalBackendUnavailableBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByTestId('local-backend-unavailable-banner')).not.toBeInTheDocument();
    expect(checkBackendReadyOnce).not.toHaveBeenCalled();
  });
});
