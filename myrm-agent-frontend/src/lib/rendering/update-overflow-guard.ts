/**
 * [INPUT]
 * - (无模块依赖) — 纯逻辑守卫，不依赖 store/React（POS: 渲染可靠性基础设施）
 *
 * [OUTPUT]
 * - isNestedUpdateOverflow: 判定错误是否为 React #185 嵌套更新溢出
 * - swallowNestedUpdateOverflow: 吸收 #185 并按源限频记录 + 持续振荡熔断
 * - registerOverflowQuench / unregisterOverflowQuench: 注册/注销源的暂停动作
 * - callWithUpdateOverflowGuard: 包装通知回调并应用守卫
 * - resetUpdateOverflowGuardForTest: 测试缝重置
 *
 * [POS]
 * 渲染可靠性基础设施。React 嵌套更新溢出（#185）的自愈守卫：吸收该错误类、
 * 限频诊断日志、对持续振荡源熔断暂停其通知通道。
 *
 * WHY THIS EXISTS — the crash is a ratchet, not a single bad component.
 * react-reconciler counts consecutive commits that each end with more
 * pending updates on the same root (`nestedUpdateCount`); once 50 commits
 * pass without one that drains the queue, the NEXT update enqueue throws
 * #185 — from whichever timer or store notification happens to fire first.
 *
 * The throw is self-healing by contract: React resets the nested-update
 * counter *before* throwing, so swallowing exactly this error class skips
 * at most one frame of rendering while the next commit starts from a clean
 * counter. That turns a view-killing crash into a dropped frame plus a
 * rate-limited diagnostic breadcrumb naming the notification source.
 *
 * This guard deliberately does NOT swallow anything else: unknown errors
 * rethrow unchanged.
 */

/** Message fragments that identify the nested-update overflow error. */
const OVERFLOW_MARKERS = ['Minified React error #185', 'Maximum update depth'] as const;

/** Window for log rate limiting (ms): first hit logs, the rest just count. */
const LOG_WINDOW_MS = 10_000;

/**
 * Circuit breaker: the same source tripping this many times inside one log
 * window is a SUSTAINED oscillation, not a one-off — absorbing alone would
 * leave the view alive but burning CPU on the oscillation's own commit
 * storm. Trip the source's quench (pause its notification channel) so
 * "alive" cannot degrade into "alive but very laggy".
 */
const TRIP_THRESHOLD = 5;

/** First quench duration (ms); doubles per consecutive trip, capped. */
const TRIP_BACKOFF_BASE_MS = 5_000;
const TRIP_BACKOFF_MAX_MS = 60_000;

/** Quench action for a source: pause its notification channel for `ms`. */
export type OverflowQuench = (ms: number) => void;

const quenches = new Map<string, OverflowQuench>();

/** Per-source state: log window + circuit-breaker bookkeeping. */
type SourceState = {
  windowStart: number;
  logged: boolean;
  count: number;
  trips: number;
  quenchUntil: number;
};

const sources = new Map<string, SourceState>();

/** Test seam: reset rate-limit and circuit-breaker bookkeeping. */
export function resetUpdateOverflowGuardForTest(): void {
  sources.clear();
}

/**
 * Register a circuit-breaker action for a source. When the source trips
 * (sustained oscillation), the quench pauses its notification channel for
 * the backoff window; the source is expected to coalesce and re-notify once
 * after the window so no data is lost. Sources without a quench only get
 * the escalated ERROR log.
 */
export function registerOverflowQuench(source: string, quench: OverflowQuench): void {
  quenches.set(source, quench);
}

export function unregisterOverflowQuench(source: string): void {
  quenches.delete(source);
}

/** Whether an error is the nested-update overflow (#185). */
export function isNestedUpdateOverflow(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return OVERFLOW_MARKERS.some((marker) => error.message.includes(marker));
}

/**
 * Swallow the nested-update overflow error, logging (rate-limited, with a
 * running count per window) which notification source surfaced it. Any
 * other error returns false so callers rethrow it untouched.
 */
export function swallowNestedUpdateOverflow(error: unknown, source: string): boolean {
  if (!isNestedUpdateOverflow(error)) return false;
  const now = Date.now();
  let state = sources.get(source);
  if (state === undefined || now - state.windowStart >= LOG_WINDOW_MS) {
    state = {
      windowStart: now,
      logged: false,
      count: 0,
      trips: state?.trips ?? 0,
      quenchUntil: state?.quenchUntil ?? 0,
    };
    sources.set(source, state);
  }
  state.count += 1;
  if (!state.logged) {
    state.logged = true;
    console.error(
      `[render-guard] Recovered from React nested-update overflow (#185) at ${source} — ` +
        `dropped 1 update, counter reset by React. If this repeats, a component ` +
        `is oscillating state updates in a tight commit chain.`,
    );
  }
  // Circuit breaker: a SUSTAINED oscillation keeps re-filling React's
  // counter between absorptions. Pause the source's notification channel
  // for an escalating window so the view cannot degrade into "alive but
  // laggy"; the source coalesces and re-notifies once after the window.
  if (state.count >= TRIP_THRESHOLD && now >= state.quenchUntil) {
    state.trips += 1;
    const ms = Math.min(TRIP_BACKOFF_BASE_MS * 2 ** (state.trips - 1), TRIP_BACKOFF_MAX_MS);
    state.quenchUntil = now + ms;
    state.count = 0;
    const quench = quenches.get(source);
    if (quench !== undefined) {
      quench(ms);
      console.error(
        `[render-guard] Sustained rendering oscillation at ${source} ` +
          `(#185 x${TRIP_THRESHOLD} in ${LOG_WINDOW_MS / 1000}s) — its notification ` +
          `channel is paused for ${ms / 1000}s to break the loop (trip #${state.trips}, ` +
          `backoff doubles). This is a bug: please report the component involved.`,
      );
    } else {
      console.error(
        `[render-guard] Sustained rendering oscillation at ${source} ` +
          `(#185 x${TRIP_THRESHOLD} in ${LOG_WINDOW_MS / 1000}s, trip #${state.trips}) — ` +
          `no quench registered for this source, absorbing only. ` +
          `This is a bug: please report the component involved.`,
      );
    }
  }
  return true;
}