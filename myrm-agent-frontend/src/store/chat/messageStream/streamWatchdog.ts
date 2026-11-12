/**
 * [INPUT]
 * None (self-contained timer; chat state is reached only through the injected `actions`)
 *
 * [OUTPUT]
 * createStreamWatchdog, StreamWatchdog, StreamWatchdogOptions, USAGE_GRACE_MS (POS: Client-side completion watchdog)
 *
 * [POS]
 * Client-side stream finished state machine watchdog.
 * Guarantees UI state self-healing whenever backend or gateway drops terminal events (e.g. Codex/custom LLM gateway
 * dropping `turn_end` / `message_end` after usage chunk): it heals when the reader reaches EOF without a terminal event,
 * and when a usage chunk is not followed by one within USAGE_GRACE_MS.
 *
 * A stream that stays open but goes quiet is not its concern: the stream reader owns transport liveness
 * (STREAM_LIVENESS_BUDGET_MS in consumeStream) and hands such a turn to the attach recovery.
 *
 * It restores UI state only. Follow-up suggestions are not requested here: a usage heal can fire while
 * the answer is still streaming, so only the terminal `message_end` knows the answer is complete.
 */

export interface StreamWatchdogOptions {
  /** Actions for mutating chat state. */
  actions: {
    setLoading: (loading: boolean) => void;
    clearActiveStream?: () => void;
    setMessageAppeared?: (appeared: boolean) => void;
    scheduleAutoSave?: () => void;
  };
}

export interface StreamWatchdog {
  notifyUsageReceived: () => void;
  markTerminalReceived: () => void;
  onReaderDone: () => void;
  dispose: () => void;
}

/** How long the terminal event may trail the usage chunk before the turn is healed. */
export const USAGE_GRACE_MS = 1500;

export function createStreamWatchdog(options: StreamWatchdogOptions): StreamWatchdog {
  let terminalReceived = false;
  let healed = false;
  let usageTimer: ReturnType<typeof setTimeout> | null = null;

  const clearUsageTimer = (): void => {
    if (usageTimer !== null) {
      clearTimeout(usageTimer);
      usageTimer = null;
    }
  };

  const triggerHeal = (reason: string): void => {
    if (terminalReceived || healed) {
      return;
    }
    healed = true;
    clearUsageTimer();

    console.warn(`[StreamWatchdog] Missing terminal event detected (${reason}). Auto-healing UI state.`);

    try {
      options.actions.setLoading(false);
      options.actions.clearActiveStream?.();
      options.actions.setMessageAppeared?.(true);

      options.actions.scheduleAutoSave?.();
    } catch (err) {
      console.error('[StreamWatchdog] Error during state self-healing:', err);
    }
  };

  return {
    notifyUsageReceived: (): void => {
      if (terminalReceived || healed) {
        return;
      }
      clearUsageTimer();
      usageTimer = setTimeout(() => {
        triggerHeal(`usage received without terminal event after ${USAGE_GRACE_MS}ms`);
      }, USAGE_GRACE_MS);
    },

    markTerminalReceived: (): void => {
      terminalReceived = true;
      clearUsageTimer();
    },

    onReaderDone: (): void => {
      clearUsageTimer();
      triggerHeal('reader reached EOF without terminal event');
    },

    dispose: clearUsageTimer,
  };
}
