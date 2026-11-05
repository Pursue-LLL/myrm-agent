import { act, renderHook } from '@testing-library/react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { dismissProactive, isProactiveDismissed, useProactiveDismissed } from '../useProactiveDismissal';

const DAY_MS = 24 * 60 * 60 * 1000;
const STORAGE_KEY = 'myrm.proactive.dismissed.demo-card';

describe('proactive dismissal memory', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('treats a card nobody closed as not dismissed', () => {
    expect(isProactiveDismissed('demo-card')).toBe(false);
  });

  it('remembers a permanent close under the shared key prefix', () => {
    dismissProactive('demo-card');

    expect(localStorage.getItem(STORAGE_KEY)).toBe('forever');
    expect(isProactiveDismissed('demo-card')).toBe(true);
    expect(isProactiveDismissed('demo-card', Date.now() + 3650 * DAY_MS)).toBe(true);
    expect(isProactiveDismissed('another-card')).toBe(false);
  });

  it('lets a snoozed card return once the snooze has run out', () => {
    const closedAt = Date.now();
    dismissProactive('demo-card', { snoozeDays: 7 });

    expect(isProactiveDismissed('demo-card', closedAt + 6 * DAY_MS)).toBe(true);
    expect(isProactiveDismissed('demo-card', closedAt + 7 * DAY_MS + 1_000)).toBe(false);
  });

  it('reads a corrupt stored value as not dismissed', () => {
    localStorage.setItem(STORAGE_KEY, 'not-a-timestamp');

    expect(isProactiveDismissed('demo-card')).toBe(false);
  });

  it('still keeps the card closed for this page when storage rejects the write', () => {
    // The test environment's storage is a polyfill that a spy on `Storage.prototype` cannot reach.
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {
        throw new DOMException('quota', 'QuotaExceededError');
      },
    });

    dismissProactive('private-mode-card');

    expect(isProactiveDismissed('private-mode-card')).toBe(true);
  });

  it('renders "open" on the server pass so hydration matches, then applies the stored close', async () => {
    dismissProactive('demo-card');
    const Probe = () => <span>{useProactiveDismissed('demo-card') ? 'closed' : 'open'}</span>;

    const container = document.createElement('div');
    container.innerHTML = renderToString(<Probe />);
    expect(container.textContent).toBe('open');

    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    let root!: ReturnType<typeof hydrateRoot>;
    await act(async () => {
      root = hydrateRoot(container, <Probe />);
    });

    expect(container.textContent).toBe('closed');
    // A hydration mismatch is reported through console.error.
    expect(consoleError).not.toHaveBeenCalled();
    act(() => root.unmount());
  });

  it('re-renders subscribers when a card is closed and when another tab closes one', () => {
    const { result } = renderHook(() => useProactiveDismissed('demo-card'));
    expect(result.current).toBe(false);

    act(() => {
      dismissProactive('demo-card');
    });
    expect(result.current).toBe(true);

    const other = renderHook(() => useProactiveDismissed('tab-card'));
    expect(other.result.current).toBe(false);
    act(() => {
      localStorage.setItem('myrm.proactive.dismissed.tab-card', 'forever');
      window.dispatchEvent(new StorageEvent('storage', { key: 'myrm.proactive.dismissed.tab-card' }));
    });
    expect(other.result.current).toBe(true);
  });
});
