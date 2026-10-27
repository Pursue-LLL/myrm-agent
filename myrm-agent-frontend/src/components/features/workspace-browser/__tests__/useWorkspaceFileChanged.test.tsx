/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FILE_CHANGE_WINDOW_MS, useWorkspaceFileChanged } from '../useWorkspaceFileChanged';

const announce = () =>
  window.dispatchEvent(new CustomEvent('workspace-file-changed', { detail: { workspace_path: '/ws' } }));
const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useWorkspaceFileChanged', () => {
  it('runs once after the window, however many events the burst held', () => {
    const onChange = vi.fn();
    renderHook(() => useWorkspaceFileChanged(onChange, true));

    for (let i = 0; i < 20; i += 1) {
      announce();
      wait(FILE_CHANGE_WINDOW_MS / 40);
    }
    expect(onChange).not.toHaveBeenCalled();
    wait(FILE_CHANGE_WINDOW_MS);

    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('keeps calling while a writer keeps going: once per window, not never', () => {
    const onChange = vi.fn();
    renderHook(() => useWorkspaceFileChanged(onChange, true));

    for (let elapsed = 0; elapsed < FILE_CHANGE_WINDOW_MS * 5; elapsed += 50) {
      announce();
      wait(50);
    }

    expect(onChange.mock.calls.length).toBeGreaterThanOrEqual(4);
    expect(onChange.mock.calls.length).toBeLessThanOrEqual(5);
  });

  it('starts a new window for the next burst', () => {
    const onChange = vi.fn();
    renderHook(() => useWorkspaceFileChanged(onChange, true));

    announce();
    wait(FILE_CHANGE_WINDOW_MS);
    announce();
    wait(FILE_CHANGE_WINDOW_MS);

    expect(onChange).toHaveBeenCalledTimes(2);
  });

  it('runs the newest callback when the window ends', () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ onChange }) => useWorkspaceFileChanged(onChange, true), {
      initialProps: { onChange: first },
    });

    announce();
    rerender({ onChange: second });
    wait(FILE_CHANGE_WINDOW_MS);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('does not listen while disabled, and stops, with its pending call, when unmounted', () => {
    const onChange = vi.fn();
    const { rerender, unmount } = renderHook(({ enabled }) => useWorkspaceFileChanged(onChange, enabled), {
      initialProps: { enabled: false },
    });
    announce();
    wait(FILE_CHANGE_WINDOW_MS * 2);
    expect(onChange).not.toHaveBeenCalled();

    rerender({ enabled: true });
    announce();
    unmount();
    wait(FILE_CHANGE_WINDOW_MS * 2);
    announce();
    wait(FILE_CHANGE_WINDOW_MS * 2);

    expect(onChange).not.toHaveBeenCalled();
  });
});
