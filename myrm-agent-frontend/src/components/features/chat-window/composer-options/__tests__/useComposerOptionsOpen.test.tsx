import { act, renderHook } from '@testing-library/react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useComposerOptionsOpen } from '../useComposerOptionsOpen';

const STORAGE_KEY = 'myrm.composer.optionsOpen';

describe('composer options region memory', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('starts closed for a viewer who never opened it', () => {
    const { result } = renderHook(() => useComposerOptionsOpen());

    expect(result.current[0]).toBe(false);
  });

  it('remembers the choice under one device-wide key', () => {
    const { result } = renderHook(() => useComposerOptionsOpen());

    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
    expect(localStorage.getItem(STORAGE_KEY)).toBe('1');

    act(() => result.current[1](false));
    expect(result.current[0]).toBe(false);
    expect(localStorage.getItem(STORAGE_KEY)).toBe('0');
  });

  it('keeps every mounted composer in step, and follows a change made in another tab', () => {
    const first = renderHook(() => useComposerOptionsOpen());
    const second = renderHook(() => useComposerOptionsOpen());

    act(() => first.result.current[1](true));
    expect(second.result.current[0]).toBe(true);

    act(() => {
      localStorage.setItem(STORAGE_KEY, '0');
      window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY }));
    });
    expect(first.result.current[0]).toBe(false);
    expect(second.result.current[0]).toBe(false);
  });

  it('renders closed on the server pass so hydration matches, then applies the saved open choice', async () => {
    localStorage.setItem(STORAGE_KEY, '1');
    const Probe = () => <span>{useComposerOptionsOpen()[0] ? 'open' : 'closed'}</span>;

    const container = document.createElement('div');
    container.innerHTML = renderToString(<Probe />);
    expect(container.textContent).toBe('closed');

    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    let root!: ReturnType<typeof hydrateRoot>;
    await act(async () => {
      root = hydrateRoot(container, <Probe />);
    });

    expect(container.textContent).toBe('open');
    // A hydration mismatch is reported through console.error.
    expect(consoleError).not.toHaveBeenCalled();
    act(() => root.unmount());
  });

  it('keeps the choice for this page when storage rejects the write, and hands back to storage afterwards', () => {
    // The test environment's storage is a polyfill that a spy on `Storage.prototype` cannot reach.
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {
        throw new DOMException('quota', 'QuotaExceededError');
      },
    });
    const { result } = renderHook(() => useComposerOptionsOpen());

    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);

    vi.unstubAllGlobals();
    act(() => result.current[1](false));
    expect(result.current[0]).toBe(false);
    expect(localStorage.getItem(STORAGE_KEY)).toBe('0');
  });
});
