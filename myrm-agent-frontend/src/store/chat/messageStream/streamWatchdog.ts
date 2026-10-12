/**
 * [INPUT]
 * ./types::StreamHandlerState, StreamHandlerActions (POS: Stream state contracts)
 *
 * [OUTPUT]
 * createStreamWatchdog, StreamWatchdog, StreamWatchdogOptions (POS: Client-side completion watchdog)
 *
 * [POS]
 * Client-side stream finished state machine watchdog.
 * Monitors SSE response silence and reader EOF to guarantee UI state self-healing
 * whenever backend or gateway drops terminal events (e.g. Codex/custom LLM gateway
 * dropping `turn_end` / `message_end` after usage chunk).
 */

/** Minimal message shape the watchdog inspects; callers keep their concrete message type via the generic. */
export interface WatchdogMessage {
  role?: string;
  content?: string;
}

export interface StreamWatchdogOptions<TMessage extends WatchdogMessage = WatchdogMessage> {
  /** Silence threshold before triggering completion watchdog (default: 3500ms). */
  silenceTimeoutMs?: number;
  /** Grace period after receiving usage event before triggering completion watchdog (default: 1500ms). */
  usageGraceMs?: number;
  /** Optional telemetry or diagnostic callback when auto-healing fires. */
  onHeal?: (reason: string) => void;
  /** State getter function. */
  getState: () => {
    loading?: boolean;
    messages?: TMessage[];
  };
  /** Actions for mutating chat state. */
  actions: {
    setLoading: (loading: boolean) => void;
    clearActiveStream?: () => void;
    setMessageAppeared?: (appeared: boolean) => void;
    _processSuggestions?: (message: TMessage) => void | Promise<void>;
    scheduleAutoSave?: () => void;
  };
}

export interface StreamWatchdog {
  feed: (eventType?: string) => void;
  notifyUsageReceived: () => void;
  markTerminalReceived: () => void;
  onReaderDone: () => void;
  isHealed: () => boolean;
  isTerminalReceived: () => boolean;
  dispose: () => void;
}

const DEFAULT_SILENCE_TIMEOUT_MS = 3500;
const DEFAULT_USAGE_GRACE_MS = 1500;

export function createStreamWatchdog<TMessage extends WatchdogMessage = WatchdogMessage>(
  options: StreamWatchdogOptions<TMessage>,
): StreamWatchdog {
  const silenceTimeoutMs = options.silenceTimeoutMs ?? DEFAULT_SILENCE_TIMEOUT_MS;
  const usageGraceMs = options.usageGraceMs ?? DEFAULT_USAGE_GRACE_MS;

  let terminalReceived = false;
  let healed = false;
  let silenceTimer: ReturnType<typeof setTimeout> | null = null;
  let usageTimer: ReturnType<typeof setTimeout> | null = null;
  let hasReceivedData = false;

  const clearTimers = (): void => {
    if (silenceTimer !== null) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
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
    clearTimers();

    console.warn(`[StreamWatchdog] Missing terminal event detected (${reason}). Auto-healing UI state.`);

    try {
      options.actions.setLoading(false);
      options.actions.clearActiveStream?.();
      options.actions.setMessageAppeared?.(true);

      const state = options.getState();
      const msgs = state.messages;
      if (Array.isArray(msgs) && msgs.length > 0) {
        const lastMsg = msgs[msgs.length - 1];
        if (lastMsg) {
          options.actions._processSuggestions?.(lastMsg);
        }
      }
      options.actions.scheduleAutoSave?.();
      options.onHeal?.(reason);
    } catch (err) {
      console.error('[StreamWatchdog] Error during state self-healing:', err);
    }
  };

  const armSilenceTimer = (): void => {
    if (terminalReceived || healed) {
      return;
    }
    if (silenceTimer !== null) {
      clearTimeout(silenceTimer);
    }
    silenceTimer = setTimeout(() => {
      if (hasReceivedData && !terminalReceived && !healed) {
        triggerHeal(`silence timeout of ${silenceTimeoutMs}ms`);
      }
    }, silenceTimeoutMs);
  };

  return {
    feed: (_eventType?: string): void => {
      if (terminalReceived || healed) {
        return;
      }
      hasReceivedData = true;
      armSilenceTimer();
    },

    notifyUsageReceived: (): void => {
      if (terminalReceived || healed) {
        return;
      }
      hasReceivedData = true;
      if (usageTimer !== null) {
        clearTimeout(usageTimer);
      }
      usageTimer = setTimeout(() => {
        if (!terminalReceived && !healed) {
          triggerHeal(`usage received without terminal event after ${usageGraceMs}ms`);
        }
      }, usageGraceMs);
    },

    markTerminalReceived: (): void => {
      terminalReceived = true;
      clearTimers();
    },

    onReaderDone: (): void => {
      clearTimers();
      if (!terminalReceived && !healed) {
        triggerHeal('reader reached EOF without terminal event');
      }
    },

    isHealed: (): boolean => healed,

    isTerminalReceived: (): boolean => terminalReceived,

    dispose: (): void => {
      clearTimers();
    },
  };
}
