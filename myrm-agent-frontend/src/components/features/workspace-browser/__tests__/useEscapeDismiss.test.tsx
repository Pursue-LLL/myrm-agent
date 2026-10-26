/** @vitest-environment jsdom */
import { fireEvent, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useEscapeDismiss } from '../useEscapeDismiss';

describe('useEscapeDismiss', () => {
  const host = vi.fn();

  beforeEach(() => {
    window.addEventListener('keydown', host);
  });

  afterEach(() => {
    window.removeEventListener('keydown', host);
    host.mockClear();
  });

  it('dismisses the layer on Escape and keeps the key from a host listening on window', () => {
    const onDismiss = vi.fn();
    renderHook(() => useEscapeDismiss(onDismiss));

    fireEvent.keyDown(document.body, { key: 'Escape' });

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(host).not.toHaveBeenCalled();
  });

  it('leaves other keys to everyone else', () => {
    const onDismiss = vi.fn();
    renderHook(() => useEscapeDismiss(onDismiss));

    fireEvent.keyDown(document.body, { key: 'Enter' });

    expect(onDismiss).not.toHaveBeenCalled();
    expect(host).toHaveBeenCalledTimes(1);
  });

  it('stops listening once the layer is gone', () => {
    const onDismiss = vi.fn();
    const { unmount } = renderHook(() => useEscapeDismiss(onDismiss));
    unmount();

    fireEvent.keyDown(document.body, { key: 'Escape' });

    expect(onDismiss).not.toHaveBeenCalled();
    expect(host).toHaveBeenCalledTimes(1);
  });
});
