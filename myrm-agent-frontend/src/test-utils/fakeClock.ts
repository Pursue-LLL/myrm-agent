/**
 * [OUTPUT]
 * settle: 让已排队的 Promise 回调与随后的 React 更新落地（真假时钟下均可用）。
 * startFakeClock / stopFakeClock: 启停 Testing Library 能驱动的 vitest 假时钟。
 * elapse: 推进假时钟并让由此触发的更新落地。
 *
 * [POS]
 * 前端测试时间控制层。Testing Library 的 asyncWrapper / waitFor 只会推进它认得的 Jest 时钟，
 * 因此假时钟启用时需用最小的 `jest` 全局向它声明 vitest 时钟。
 */

import { act } from '@testing-library/react';
import { vi } from 'vitest';

/** 让已排队的 Promise 回调与随后的 React 更新落地（假时钟下改为推进 0ms）。 */
export const settle = () =>
  act(async () => {
    if (vi.isFakeTimers()) {
      await vi.advanceTimersByTimeAsync(0);
    } else {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });

export function startFakeClock(): void {
  vi.useFakeTimers();
  vi.stubGlobal('jest', { advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms) });
}

export function stopFakeClock(): void {
  vi.useRealTimers();
  vi.unstubAllGlobals();
}

/** 推进假时钟，并让由此触发的一切更新落地。 */
export const elapse = (ms: number) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
