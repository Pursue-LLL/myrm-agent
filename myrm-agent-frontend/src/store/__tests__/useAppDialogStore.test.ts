import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAppDialogStore, type AppDialogSpec } from '../useAppDialogStore';

const confirmSpec = (description: string): AppDialogSpec => ({ kind: 'confirm', variant: 'warning', description });

const state = () => useAppDialogStore.getState();
const currentId = (): number => {
  const current = state().current;
  if (!current) {
    throw new Error('no dialog is showing');
  }
  return current.id;
};

describe('useAppDialogStore', () => {
  beforeEach(() => {
    useAppDialogStore.setState({ current: null, open: false, queue: [] });
  });

  it('shows the first request right away', () => {
    state().enqueue(confirmSpec('first'), vi.fn());

    expect(state().open).toBe(true);
    expect(state().current?.spec).toMatchObject({ description: 'first' });
    expect(state().queue).toHaveLength(0);
  });

  it('keeps later requests behind the one on screen, in arrival order', () => {
    state().enqueue(confirmSpec('first'), vi.fn());
    state().enqueue(confirmSpec('second'), vi.fn());
    state().enqueue(confirmSpec('third'), vi.fn());

    expect(state().current?.spec).toMatchObject({ description: 'first' });
    expect(state().queue.map((dialog) => dialog.spec)).toEqual([
      expect.objectContaining({ description: 'second' }),
      expect.objectContaining({ description: 'third' }),
    ]);
  });

  it('hands the answer to the request it belongs to and moves on to the next one', () => {
    const first = vi.fn();
    const second = vi.fn();
    state().enqueue(confirmSpec('first'), first);
    state().enqueue(confirmSpec('second'), second);

    state().settle(currentId(), true);

    expect(first).toHaveBeenCalledExactlyOnceWith(true);
    expect(second).not.toHaveBeenCalled();
    expect(state().open).toBe(true);
    expect(state().current?.spec).toMatchObject({ description: 'second' });
    expect(state().queue).toHaveLength(0);
  });

  it('closes after the last answer but keeps the content for the exit animation', () => {
    state().enqueue(confirmSpec('only'), vi.fn());
    const id = currentId();

    state().settle(id, null);

    expect(state().open).toBe(false);
    expect(state().current?.id).toBe(id);
  });

  it('answers a request once, however many times its dialog reports closing', () => {
    const answer = vi.fn();
    state().enqueue(confirmSpec('only'), answer);
    const id = currentId();

    state().settle(id, true);
    state().settle(id, null);
    state().settle(id, false);

    expect(answer).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('ignores a late answer from a dialog that has already been replaced', () => {
    const first = vi.fn();
    const second = vi.fn();
    state().enqueue(confirmSpec('first'), first);
    state().enqueue(confirmSpec('second'), second);
    const firstId = currentId();
    state().settle(firstId, true);

    // The first dialog is still animating out and reports that it closed.
    state().settle(firstId, null);

    expect(second).not.toHaveBeenCalled();
    expect(state().open).toBe(true);
    expect(state().current?.spec).toMatchObject({ description: 'second' });
  });

  it('ignores an answer for a request nobody is showing', () => {
    const answer = vi.fn();
    state().enqueue(confirmSpec('first'), answer);

    state().settle(currentId() + 100, true);

    expect(answer).not.toHaveBeenCalled();
    expect(state().open).toBe(true);
  });

  it('shows a new request immediately once the previous dialog has closed', () => {
    state().enqueue(confirmSpec('first'), vi.fn());
    state().settle(currentId(), true);

    state().enqueue(confirmSpec('second'), vi.fn());

    expect(state().open).toBe(true);
    expect(state().current?.spec).toMatchObject({ description: 'second' });
    expect(state().queue).toHaveLength(0);
  });

  it('numbers every request differently, so an answer can only match its own dialog', () => {
    state().enqueue(confirmSpec('first'), vi.fn());
    const firstId = currentId();
    state().settle(firstId, true);
    state().enqueue(confirmSpec('second'), vi.fn());

    expect(currentId()).not.toBe(firstId);
  });
});
