import { render, screen, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

let mockPathname = '/';

vi.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

vi.mock('../AppLayout', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="app-layout">{children}</div>
  ),
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
  shouldShowBootScreen: vi.fn(),
}));

import PageLayout from '../PageLayout';
import { shouldShowBootScreen } from '../../features/app-shell/boot-screen';

const mockShouldShowBootScreen = vi.mocked(shouldShowBootScreen);

describe('PageLayout', () => {
  beforeEach(() => {
    mockPathname = '/';
    vi.clearAllMocks();
  });

  it('renders null before client mount', () => {
    mockShouldShowBootScreen.mockReturnValue(true);
    const { container } = render(
      <PageLayout>
        <span>child</span>
      </PageLayout>,
    );
    expect(container.firstChild).toBeNull();
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
