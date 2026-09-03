'use client';

/**
 * [INPUT]
 * - lib/rendering/update-overflow-guard.ts (POS: 渲染可靠性基础设施，#185 自愈守卫)
 *
 * [OUTPUT]
 * - useStoreSnapshot: 高频流式热路径手动订阅 hook（DefaultLane 化唤醒 + 熔断 pause 门 + macrotask 补发）
 *
 * [POS]
 * 跨域复用 hook。以手动订阅替代 useSyncExternalStore 订阅高频流式「version-counter」热路径，
 * 唤醒走 DefaultLane 并入在途渲染，消除嵌套更新棘轮；通知回调经 #185 守卫包装。
 *
 * useStoreSnapshot — manual store subscription for high-frequency streaming
 * hot paths.
 *
 * WHY NOT useSyncExternalStore — every store notification routed through
 * useSyncExternalStore forces a SYNCLANE re-render. During streaming, that
 * sync render preempts/discards whatever DefaultLane render is in flight;
 * every such sync commit then ends with Default work still pending, which
 * React's commit-end accounting counts as a NESTED update. 50 consecutive
 * dirty commits throw "Maximum update depth exceeded" (#185) from whichever
 * timer dispatches next, killing the chat view.
 *
 * A manual subscription dispatches setState from the notification callback
 * at DEFAULT lane instead: the wakeup coalesces into the in-flight render
 * instead of preempting it, commits end clean, and the counter resets.
 * The instance's notification channel is registered with the #185 guard's
 * circuit breaker (see @/lib/rendering): a sustained oscillation at this
 * source pauses the channel (notifications are dropped, not queued) for the
 * backoff window; the next post-window store write re-syncs the view, so
 * "alive" cannot degrade into "alive but very laggy" and no data is lost.
 *
 * State holds the store snapshot itself (reference-compared, immutable
 * updates from zustand) — snapshot semantics are identical to
 * useSyncExternalStore including bail-out when the slice is unchanged and
 * one-beat-stale reads corrected by the next notification.
 *
 * Use ONLY for high-frequency hot paths where staleness-by-one-notification
 * is acceptable (the next notification corrects it). For low-frequency
 * precise states keep useSyncExternalStore.
 *
 * @param subscribe - store subscribe(fn) → unsubscribe.
 * @param getSnapshot - returns the (referentially stable) store slice.
 * @param getServerSnapshot - snapshot used for the SSR/hydration initial state.
 * @param resubscribeKey - when it changes, re-subscribes and catches up
 *   (pass the store's active id so subscription follows slice switches).
 * @returns The latest store snapshot.
 */
import { useEffect, useRef, useState } from 'react';
import {
  registerOverflowQuench,
  swallowNestedUpdateOverflow,
  unregisterOverflowQuench,
} from '@/lib/rendering/update-overflow-guard';

/**
 * Module-level pause gate shared by all instances of this source: when the
 * circuit breaker trips, quench(ms) extends this deadline; notifications
 * arriving while paused are dropped (not queued) and the next post-window
 * store write re-syncs the snapshot, so pausing loses no data.
 */
let pausedUntil = 0;

/** Live instances of this source; the quench registration is released only
 * when the last instance unmounts (multi-instance safe). */
let instanceCount = 0;

const SOURCE = 'useStoreSnapshot';

export function useStoreSnapshot<T>(
  subscribe: (listener: () => void) => () => void,
  getSnapshot: () => T,
  getServerSnapshot?: () => T,
  resubscribeKey?: string | number | null,
): T {
  const [snapshot, setSnapshot] = useState<T>(() => getServerSnapshot ?? getSnapshot);

  // Latest-refs, NOT effect deps: callers pass inline closures (e.g.
  // `() => useChatStore.getState().messages`), and a fresh reference per
  // render would re-run the effect after EVERY render — re-subscribing and
  // dispatching setSnapshot from the passive effect, chaining passive
  // updates until React throws #185. Subscribe exactly once per key; the
  // listener reads fresh getters through the ref.
  const latest = useRef({ subscribe, getSnapshot });
  latest.current = { subscribe, getSnapshot };

  useEffect(() => {
    // Catch up on any change between the first render and this effect's
    // mount (and after a key-driven re-subscribe) — the subscription alone
    // would miss it.
    setSnapshot(latest.current.getSnapshot());
    const unsubscribe = latest.current.subscribe(() => {
      if (Date.now() < pausedUntil) {
        return;
      }
      try {
        setSnapshot(latest.current.getSnapshot());
      } catch (error) {
        // #185 absorbed: the dropped wakeup is re-issued on the next
        // macrotask from the store snapshot, so the view can lag at most
        // one frame and never stays stale.
        if (swallowNestedUpdateOverflow(error, SOURCE)) {
          setTimeout(() => setSnapshot(latest.current.getSnapshot()), 0);
          return;
        }
        throw error;
      }
    });
    registerOverflowQuench(SOURCE, (ms: number) => {
      pausedUntil = Date.now() + ms;
    });
    instanceCount += 1;
    return () => {
      instanceCount -= 1;
      if (instanceCount <= 0) {
        unregisterOverflowQuench(SOURCE);
      }
      unsubscribe();
    };
  }, [resubscribeKey]);

  return snapshot;
}
