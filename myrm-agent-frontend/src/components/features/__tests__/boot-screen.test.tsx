import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import BootScreen from '../app-shell/boot-screen';
import { shouldShowBootScreen, markBootScreenShown } from '../app-shell/boot-screen-gate';

vi.mock('next/image', () => ({
  default: (props: Record<string, unknown>) => <img {...props} />,
}));

vi.mock('@/lib/backend-health', () => ({
  waitForBackendReady: vi.fn(() => Promise.resolve(true)),
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

const FADE_DURATION_MS = 400;
const AUTO_FINISH_MS = 500 + 4 * 120 + 340 + FADE_DURATION_MS;

async function finishBootSequence(onComplete: ReturnType<typeof vi.fn>) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(AUTO_FINISH_MS);
  });
  expect(onComplete).toHaveBeenCalledTimes(1);
}

async function skipBootSequence(onComplete: ReturnType<typeof vi.fn>) {
  const container = screen.getByRole('presentation');
  await act(async () => {
    fireEvent.click(container);
    await vi.advanceTimersByTimeAsync(FADE_DURATION_MS);
  });
  expect(onComplete).toHaveBeenCalledTimes(1);
}

describe('shouldShowBootScreen', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('returns true when sessionStorage has no key', () => {
    expect(shouldShowBootScreen()).toBe(true);
  });

  it('returns false when sessionStorage has the key', () => {
    sessionStorage.setItem('myrm_boot_shown', '1');
    expect(shouldShowBootScreen()).toBe(false);
  });
});

describe('markBootScreenShown', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('sets sessionStorage key', () => {
    markBootScreenShown();
    expect(sessionStorage.getItem('myrm_boot_shown')).toBe('1');
  });

  it('silently handles sessionStorage write failures', () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('QuotaExceededError');
    });

    expect(() => markBootScreenShown()).not.toThrow();
    setItemSpy.mockRestore();
  });
});

describe('BootScreen component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders logo and title', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    expect(screen.getByTestId('boot-screen')).toBeInTheDocument();
    expect(screen.getByAltText('MyrmAgent')).toBeInTheDocument();
    expect(screen.getByText('title')).toBeInTheDocument();
  });

  it('reveals logo after 80ms and title after 300ms', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    const logoWrapper = screen.getByAltText('MyrmAgent').parentElement;
    const title = screen.getByText('title');

    expect(logoWrapper).toHaveClass('opacity-0');
    expect(title).toHaveClass('opacity-0');

    act(() => {
      vi.advanceTimersByTime(80);
    });
    expect(logoWrapper).toHaveClass('opacity-100');

    act(() => {
      vi.advanceTimersByTime(220);
    });
    expect(title).toHaveClass('opacity-100');
  });

  it('shows boot steps progressively', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    expect(screen.queryByText('step.loadingTheme')).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(screen.getByText('step.loadingTheme')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(120);
    });
    expect(screen.getByText('step.syncingSettings')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(120);
    });
    expect(screen.getByText('step.initServices')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(120);
    });
    expect(screen.getByText('step.ready')).toBeInTheDocument();
  });

  it('hides skip hint before first step appears', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    const skipHint = screen.getByText('skipHint');
    expect(skipHint).toHaveClass('opacity-0');
  });

  it('shows skip hint after first step', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    act(() => {
      vi.advanceTimersByTime(500);
    });
    const skipHint = screen.getByText('skipHint');
    expect(skipHint).toHaveClass('opacity-100');
  });

  it('styles last step as primary and shows pulse on current step', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    act(() => {
      vi.advanceTimersByTime(620);
    });

    expect(screen.getByText('step.loadingTheme').parentElement).toHaveClass('text-muted-foreground');
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(240);
    });
    expect(screen.getByText('step.ready').parentElement).toHaveClass('brand-gradient-text', 'font-medium');
  });

  it('calls onComplete after animation completes', async () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);
    await finishBootSequence(onComplete);
  });

  it('calls onComplete on click (skip)', async () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);
    await skipBootSequence(onComplete);
  });

  it('marks sessionStorage on complete', async () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);
    await finishBootSequence(onComplete);
    expect(sessionStorage.getItem('myrm_boot_shown')).toBe('1');
  });

  it('does not call onComplete twice on click then auto-finish', async () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    await act(async () => {
      fireEvent.click(screen.getByRole('presentation'));
      await vi.advanceTimersByTimeAsync(AUTO_FINISH_MS);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('does not call onComplete twice on double ESC', async () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    await act(async () => {
      fireEvent.keyDown(window, { key: 'Escape' });
      fireEvent.keyDown(window, { key: 'Escape' });
      await vi.advanceTimersByTimeAsync(FADE_DURATION_MS);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('calls onComplete on ESC key press', async () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    await act(async () => {
      fireEvent.keyDown(window, { key: 'Escape' });
      await vi.advanceTimersByTimeAsync(FADE_DURATION_MS);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem('myrm_boot_shown')).toBe('1');
  });

  it('ignores non-Escape key presses', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    act(() => {
      fireEvent.keyDown(window, { key: 'Enter' });
    });

    expect(onComplete).not.toHaveBeenCalled();
  });

  it('applies fade-out class and transition duration after finish', async () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    const container = screen.getByRole('presentation');
    expect(container).toHaveClass('opacity-100');
    expect(container).toHaveStyle({ transitionDuration: '400ms' });

    await act(async () => {
      fireEvent.click(container);
    });

    expect(container).toHaveClass('opacity-0');
  });

  it('cleans up timers and event listener on unmount', () => {
    const onComplete = vi.fn();
    const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');

    const { unmount } = render(<BootScreen onComplete={onComplete} />);
    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith('keydown', expect.any(Function));
    removeEventListenerSpy.mockRestore();
  });

  it('does not call onComplete if unmounted before finish', () => {
    const onComplete = vi.fn();
    const { unmount } = render(<BootScreen onComplete={onComplete} />);

    act(() => {
      vi.advanceTimersByTime(200);
    });
    unmount();

    act(() => {
      vi.advanceTimersByTime(AUTO_FINISH_MS);
    });
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('renders checkmark icons for completed steps', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    act(() => {
      vi.advanceTimersByTime(800);
    });

    const svgs = document.querySelectorAll('svg');
    expect(svgs.length).toBeGreaterThan(0);
  });

  it('shows backend setup hint when local backend health check fails', async () => {
    const { waitForBackendReady } = await import('@/lib/backend-health');
    vi.mocked(waitForBackendReady).mockResolvedValueOnce(false);

    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('boot-backend-setup-hint')).toHaveTextContent('hintUnreachable');
  });

  it('does not show backend setup hint outside local mode', async () => {
    const { isLocalMode } = await import('@/lib/deploy-mode');
    const { waitForBackendReady } = await import('@/lib/backend-health');
    vi.mocked(isLocalMode).mockReturnValueOnce(false);
    vi.mocked(waitForBackendReady).mockResolvedValueOnce(false);

    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByTestId('boot-backend-setup-hint')).not.toBeInTheDocument();
  });
});
