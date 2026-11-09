import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { setShowSystemMessages, useShowSystemMessages } from '../useShowSystemMessages';

const SWITCH_STORAGE_KEY = 'developer_show_system_messages';

// The developer settings persist the switch first, then announce it.
function announceSwitch(on: boolean): void {
  localStorage.setItem(SWITCH_STORAGE_KEY, String(on));
  window.dispatchEvent(new CustomEvent('developer-mode-changed', { detail: { showSystemMessages: on } }));
}

function renderTracked(): { renders: boolean[]; unmount: () => void } {
  const renders: boolean[] = [];
  const { unmount } = renderHook(() => {
    const shown = useShowSystemMessages();
    renders.push(shown);
    return shown;
  });
  return { renders, unmount };
}

describe('useShowSystemMessages', () => {
  afterEach(() => {
    localStorage.removeItem(SWITCH_STORAGE_KEY);
  });

  it('is off while developer mode was never switched on', () => {
    const { result } = renderHook(() => useShowSystemMessages());

    expect(result.current).toBe(false);
  });

  it('reads a switch that is already on in the very first render', () => {
    localStorage.setItem(SWITCH_STORAGE_KEY, 'true');

    const { renders } = renderTracked();

    expect(renders[0]).toBe(true);
  });

  it('follows the switch each time the developer settings announce a change', () => {
    const { result } = renderHook(() => useShowSystemMessages());

    act(() => announceSwitch(true));
    expect(result.current).toBe(true);

    act(() => announceSwitch(false));
    expect(result.current).toBe(false);
  });

  it('persists the switch under the stored key and makes a mounted reader follow it', () => {
    const { result } = renderHook(() => useShowSystemMessages());

    act(() => setShowSystemMessages(true));
    expect(localStorage.getItem(SWITCH_STORAGE_KEY)).toBe('true');
    expect(result.current).toBe(true);

    act(() => setShowSystemMessages(false));
    expect(localStorage.getItem(SWITCH_STORAGE_KEY)).toBe('false');
    expect(result.current).toBe(false);
  });

  it('keeps every mounted reader in step with a single write', () => {
    const first = renderHook(() => useShowSystemMessages());
    const second = renderHook(() => useShowSystemMessages());

    act(() => setShowSystemMessages(true));

    expect(first.result.current).toBe(true);
    expect(second.result.current).toBe(true);
  });

  it('stops following the switch once the component is gone', () => {
    const { renders, unmount } = renderTracked();
    unmount();
    const rendersAtUnmount = renders.length;

    act(() => announceSwitch(true));

    expect(renders).toHaveLength(rendersAtUnmount);
  });
});
