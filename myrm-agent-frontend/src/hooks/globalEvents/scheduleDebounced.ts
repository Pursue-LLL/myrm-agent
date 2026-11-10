/**
 * [INPUT]
 * - ./eventTypes::DebounceTimers (POS: 防抖计时器表)
 *
 * [OUTPUT]
 * - scheduleDebounced: 同一 key 的连续触发合并为最后一次触发后 delayMs 执行一次 task
 *
 * [POS]
 * 全局事件刷新类处理器的防抖原语：事件常成串到达，只在静默后刷新一次。
 */
import type { DebounceTimers } from './eventTypes';

export function scheduleDebounced(timers: DebounceTimers, key: string, delayMs: number, task: () => void): void {
  clearTimeout(timers.current[key]);
  timers.current[key] = setTimeout(() => {
    task();
    delete timers.current[key];
  }, delayMs);
}
