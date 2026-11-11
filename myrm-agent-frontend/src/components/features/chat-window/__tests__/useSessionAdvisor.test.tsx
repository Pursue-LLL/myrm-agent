/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useSessionAdvisor } from '../useSessionAdvisor';

const ADVISOR_EVENT = 'copilot-open-advisor';

const requestAdvisor = (detail?: { question?: string; selection?: string }) =>
  act(() => {
    window.dispatchEvent(new CustomEvent(ADVISOR_EVENT, { detail }));
  });

describe('useSessionAdvisor', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts closed with no context', () => {
    const { result } = renderHook(() => useSessionAdvisor());

    expect(result.current).toMatchObject({ open: false, question: '', selection: undefined });
  });

  it('opens with the question and the selected text the request carries', () => {
    const { result } = renderHook(() => useSessionAdvisor());

    requestAdvisor({ question: 'Is this safe to ship?', selection: 'rm -rf build' });

    expect(result.current).toMatchObject({
      open: true,
      question: 'Is this safe to ship?',
      selection: 'rm -rf build',
    });
  });

  it('opens empty when the request carries nothing', () => {
    const { result } = renderHook(() => useSessionAdvisor());

    requestAdvisor();

    expect(result.current).toMatchObject({ open: true, question: '', selection: undefined });
  });

  it('replaces the earlier context when a new request arrives while open', () => {
    const { result } = renderHook(() => useSessionAdvisor());
    requestAdvisor({ question: 'first', selection: 'old' });

    requestAdvisor({ question: 'second' });

    expect(result.current).toMatchObject({ open: true, question: 'second', selection: undefined });
  });

  it('forgets the question and the selection once closed, so the next opening starts clean', () => {
    const { result } = renderHook(() => useSessionAdvisor());
    requestAdvisor({ question: 'Is this safe to ship?', selection: 'rm -rf build' });

    act(() => result.current.onOpenChange(false));
    expect(result.current).toMatchObject({ open: false, question: '', selection: undefined });

    requestAdvisor();
    expect(result.current).toMatchObject({ open: true, question: '', selection: undefined });
  });

  it('keeps the context while it is told to stay open', () => {
    const { result } = renderHook(() => useSessionAdvisor());
    requestAdvisor({ question: 'keep me', selection: 'this too' });

    act(() => result.current.onOpenChange(true));

    expect(result.current).toMatchObject({ open: true, question: 'keep me', selection: 'this too' });
  });

  it('stops listening for requests once unmounted', () => {
    const add = vi.spyOn(window, 'addEventListener');
    const remove = vi.spyOn(window, 'removeEventListener');
    const { unmount } = renderHook(() => useSessionAdvisor());
    const handler = add.mock.calls.find(([type]) => String(type) === ADVISOR_EVENT)?.[1];

    unmount();

    expect(handler).toBeDefined();
    expect(remove).toHaveBeenCalledWith(ADVISOR_EVENT, handler);
  });
});
