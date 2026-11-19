import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { withTimeout } from '../withTimeout';

describe('withTimeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('hands over the value of a promise that settles within the limit and leaves no timer behind', async () => {
    await expect(withTimeout(Promise.resolve('value'), 1000)).resolves.toBe('value');

    await vi.advanceTimersByTimeAsync(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('rejects with the error of a promise that fails within the limit and leaves no timer behind', async () => {
    const failure = new Error('failed');

    await expect(withTimeout(Promise.reject(failure), 1000)).rejects.toBe(failure);

    await vi.advanceTimersByTimeAsync(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('rejects exactly when the limit passes', async () => {
    const settled = vi.fn();
    withTimeout(new Promise<never>(() => undefined), 3000).then(settled, settled);

    await vi.advanceTimersByTimeAsync(2999);
    expect(settled).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(settled).toHaveBeenCalledTimes(1);
    expect(settled.mock.calls[0][0]).toMatchObject({ message: 'timed out after 3000 ms' });
  });

  it('ignores what the promise does after the limit, including a late rejection', async () => {
    let succeedLate!: (value: string) => void;
    let failLate!: (error: Error) => void;
    const lateValue = new Promise<string>((resolve) => {
      succeedLate = resolve;
    });
    const lateFailure = new Promise<string>((_resolve, reject) => {
      failLate = reject;
    });
    const settled = vi.fn();
    withTimeout(lateValue, 100).then(settled, settled);
    withTimeout(lateFailure, 100).then(settled, settled);
    await vi.advanceTimersByTimeAsync(100);
    expect(settled).toHaveBeenCalledTimes(2);

    succeedLate('late');
    failLate(new Error('late'));
    await vi.advanceTimersByTimeAsync(0);

    expect(settled).toHaveBeenCalledTimes(2);
    expect(
      settled.mock.calls.every(([outcome]) => outcome instanceof Error && outcome.message.startsWith('timed out')),
    ).toBe(true);
  });
});
