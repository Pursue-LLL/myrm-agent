import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useReasoningAutoCollapse } from '../useReasoningAutoCollapse';

type Props = Parameters<typeof useReasoningAutoCollapse>[0];

const THINKING: Props = { isLast: true, loading: true, content: '', reasoning: 'plan first', displayMode: 'collapsed' };

function mountHook(initial: Props = THINKING) {
  return renderHook((props: Props) => useReasoningAutoCollapse(props), { initialProps: initial });
}

function advance(ms: number): void {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

describe('useReasoningAutoCollapse', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts open while the latest answer is still only thinking', () => {
    expect(mountHook().result.current.isExpanded).toBe(true);
  });

  it.each([
    ['an earlier answer', { isLast: false }],
    ['an answer that is not streaming', { loading: false }],
    ['an answer that already has text', { content: 'text' }],
  ])('starts closed for %s', (_name, override) => {
    expect(mountHook({ ...THINKING, ...override }).result.current.isExpanded).toBe(false);
  });

  it('folds once the answer has been still for a second, and stays open when the reader reopens it', () => {
    const { result, rerender } = mountHook();

    rerender({ ...THINKING, content: 'Hello' });
    advance(999);
    expect(result.current.isExpanded).toBe(true);
    advance(1);
    expect(result.current.isExpanded).toBe(false);

    act(() => result.current.toggle());
    advance(5000);

    expect(result.current.isExpanded).toBe(true);
  });

  it('waits again while the answer keeps changing', () => {
    const { result, rerender } = mountHook();

    rerender({ ...THINKING, content: 'Hel' });
    advance(600);
    rerender({ ...THINKING, content: 'Hello' });
    advance(600);
    expect(result.current.isExpanded).toBe(true);

    advance(400);

    expect(result.current.isExpanded).toBe(false);
  });

  it('never folds the reasoning shown inline', () => {
    const { result, rerender } = mountHook({ ...THINKING, displayMode: 'inline' });

    rerender({ ...THINKING, displayMode: 'inline', content: 'Hello' });
    advance(5000);

    expect(result.current.isExpanded).toBe(true);
  });

  it('keeps a block open when the message has no reasoning to fold', () => {
    const { result, rerender } = mountHook({ ...THINKING, reasoning: undefined });

    rerender({ ...THINKING, reasoning: undefined, content: 'Hello' });
    advance(5000);

    expect(result.current.isExpanded).toBe(true);
  });

  it('flips on toggle', () => {
    const { result } = mountHook({ ...THINKING, isLast: false });

    act(() => result.current.toggle());
    expect(result.current.isExpanded).toBe(true);

    act(() => result.current.toggle());
    expect(result.current.isExpanded).toBe(false);
  });
});
