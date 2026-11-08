import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ExpiryCountdown } from '../ExpiryCountdown';
import { BARE_DESTRUCTIVE_TEXT } from './approvalKit';

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);

const NOW = new Date('2026-01-01T00:00:00.000Z');
const inMs = (ms: number) => new Date(NOW.getTime() + ms).toISOString();

const MUTED = 'text-muted-foreground';
const URGENT = 'text-amber-600';
const EXPIRED = 'text-destructive-text';

const renderCountdown = (expiresAt: string) => {
  const view = render(<ExpiryCountdown expiresAt={expiresAt} />);
  const badge = () => view.container.querySelector('[aria-live="polite"]') as HTMLElement;
  return { ...view, badge };
};

describe('ExpiryCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('shows minutes and zero-padded seconds while more than a minute is left', () => {
    const { badge } = renderCountdown(inMs(125_000));

    expect(badge().textContent).toBe('2:05');
    expect(badge().className).toContain(MUTED);
    expect(badge().className).not.toContain(URGENT);
  });

  it('rounds the seconds left up and turns amber under a minute', () => {
    const { badge } = renderCountdown(inMs(45_200));

    expect(badge().textContent).toBe('toolApproval.expiresIn:{"seconds":46}');
    expect(badge().className).toContain(URGENT);
    expect(badge().className).not.toContain(MUTED);
  });

  it('is still muted at exactly a minute and amber from the first millisecond below it', () => {
    const atMinute = renderCountdown(inMs(60_000));
    expect(atMinute.badge().textContent).toBe('1:00');
    expect(atMinute.badge().className).toContain(MUTED);
    atMinute.unmount();

    const lastMoment = renderCountdown(inMs(1));
    expect(lastMoment.badge().textContent).toBe('toolApproval.expiresIn:{"seconds":1}');
    expect(lastMoment.badge().className).toContain(URGENT);
  });

  it.each([0, -5_000])('reads expired in the destructive text colour when %i ms are left', (remaining) => {
    const { badge } = renderCountdown(inMs(remaining));

    expect(badge().textContent).toBe('toolApproval.expired');
    expect(badge().className).toContain(EXPIRED);
    expect(badge().className).not.toMatch(BARE_DESTRUCTIVE_TEXT);
    expect(badge().className).not.toContain(MUTED);
    expect(badge().className).not.toContain(URGENT);
  });

  it('renders nothing for a date it cannot read', () => {
    const { container } = renderCountdown('not a date');

    expect(container.firstChild).toBeNull();
  });

  it('counts down every second until it has expired', () => {
    const { badge } = renderCountdown(inMs(61_000));
    expect(badge().textContent).toBe('1:01');

    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(badge().textContent).toBe('1:00');
    expect(badge().className).toContain(MUTED);

    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(badge().textContent).toBe('toolApproval.expiresIn:{"seconds":59}');
    expect(badge().className).toContain(URGENT);

    act(() => {
      vi.advanceTimersByTime(59_000);
    });
    expect(badge().textContent).toBe('toolApproval.expired');
    expect(badge().className).toContain(EXPIRED);
  });

  it('follows a new expiry date', () => {
    const { badge, rerender } = renderCountdown(inMs(125_000));

    rerender(<ExpiryCountdown expiresAt={inMs(30_000)} />);

    expect(badge().textContent).toBe('toolApproval.expiresIn:{"seconds":30}');
  });

  it('stops its timer when it unmounts', () => {
    const { unmount } = renderCountdown(inMs(125_000));
    expect(vi.getTimerCount()).toBe(1);

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
