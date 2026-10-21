/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useCopyFeedback } from '../useCopyFeedback';

const writeToClipboard = vi.hoisted(() => vi.fn());

vi.mock('@/lib/utils/clipboardUtils', () => ({ writeToClipboard }));

describe('useCopyFeedback', () => {
  async function copy(hook: { result: { current: ReturnType<typeof useCopyFeedback> } }, text: string) {
    await act(async () => {
      await hook.result.current.copy(text);
    });
  }

  async function advance(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }

  beforeEach(() => {
    vi.useFakeTimers();
    writeToClipboard.mockReset();
    writeToClipboard.mockResolvedValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('copies silently through the shared clipboard helper and confirms for two seconds', async () => {
    const hook = renderHook(() => useCopyFeedback());
    expect(hook.result.current.copied).toBe(false);

    await copy(hook, 'ABCD-1234');

    expect(writeToClipboard).toHaveBeenCalledExactlyOnceWith('ABCD-1234', true);
    expect(hook.result.current.copied).toBe(true);

    await advance(1999);
    expect(hook.result.current.copied).toBe(true);
    await advance(1);
    expect(hook.result.current.copied).toBe(false);
  });

  it('honors a custom confirmation window', async () => {
    const hook = renderHook(() => useCopyFeedback(500));

    await copy(hook, 'x');
    await advance(499);
    expect(hook.result.current.copied).toBe(true);
    await advance(1);
    expect(hook.result.current.copied).toBe(false);
  });

  it('does not confirm a copy the clipboard refused', async () => {
    writeToClipboard.mockResolvedValue(false);
    const hook = renderHook(() => useCopyFeedback());

    await copy(hook, 'ABCD-1234');

    expect(hook.result.current.copied).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('restarts the window when copied again before it ends', async () => {
    const hook = renderHook(() => useCopyFeedback());

    await copy(hook, 'ABCD-1234');
    await advance(1500);
    await copy(hook, 'ABCD-1234');

    await advance(1999);
    expect(hook.result.current.copied).toBe(true);
    await advance(1);
    expect(hook.result.current.copied).toBe(false);
  });

  it('leaves no timer behind after unmount, even for a copy that settles late', async () => {
    let settle: (written: boolean) => void = () => {};
    writeToClipboard.mockReturnValue(new Promise<boolean>((resolve) => (settle = resolve)));
    const hook = renderHook(() => useCopyFeedback());

    const pending = hook.result.current.copy('ABCD-1234');
    hook.unmount();
    await act(async () => {
      settle(true);
      await pending;
    });

    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears the pending confirmation on unmount', async () => {
    const hook = renderHook(() => useCopyFeedback());
    await copy(hook, 'ABCD-1234');
    expect(vi.getTimerCount()).toBe(1);

    hook.unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
