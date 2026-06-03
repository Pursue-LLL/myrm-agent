import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import BootScreen, { shouldShowBootScreen, markBootScreenShown } from '../app-shell/boot-screen';

vi.mock('next/image', () => ({
  default: (props: Record<string, unknown>) => <img {...props} />,
}));

const AUTO_FINISH_MS = 500 + 4 * 120 + 340 + 400;

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

  it('calls onComplete after animation completes', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    act(() => {
      vi.advanceTimersByTime(AUTO_FINISH_MS);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('calls onComplete on click (skip)', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    const container = screen.getByRole('presentation');
    act(() => {
      fireEvent.click(container);
    });

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('marks sessionStorage on complete', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    act(() => {
      vi.advanceTimersByTime(AUTO_FINISH_MS);
    });
    expect(sessionStorage.getItem('myrm_boot_shown')).toBe('1');
  });

  it('does not call onComplete twice on click then auto-finish', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    const container = screen.getByRole('presentation');
    act(() => {
      fireEvent.click(container);
    });

    act(() => {
      vi.advanceTimersByTime(AUTO_FINISH_MS);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('does not call onComplete twice on double ESC', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
      fireEvent.keyDown(window, { key: 'Escape' });
    });

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('calls onComplete on ESC key press', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });

    act(() => {
      vi.advanceTimersByTime(400);
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

  it('applies fade-out class and transition duration after finish', () => {
    const onComplete = vi.fn();
    render(<BootScreen onComplete={onComplete} />);

    const container = screen.getByRole('presentation');
    expect(container).toHaveClass('opacity-100');
    expect(container).toHaveStyle({ transitionDuration: '400ms' });

    act(() => {
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
});
