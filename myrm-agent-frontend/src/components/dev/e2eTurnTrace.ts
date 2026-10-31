/**
 * [INPUT]
 * - none (pure; the caller supplies the clock)
 *
 * [OUTPUT]
 * - createTurnTrace: per-send record of the SSE events the page received (type, first/last time, count) and how
 *   the send promise ended
 * - TurnTrace / TurnTraceSnapshot / TurnTraceEntry / TurnTraceSettle
 *
 * [POS]
 * E2E bridge diagnostics. At `send-turn-observe-timeout` the page's `streaming` flag cannot tell a turn that is
 * still starting from one that ended without output (the stream watchdog turns it off 3.5 s after the last event
 * while the model still works); this record can.
 */

export interface TurnTraceEntry {
  type: string;
  /** Time of the first event of this run, in ms after the trace started. */
  atMs: number;
  /** Time of the last event folded into this entry, in ms after the trace started. */
  lastAtMs: number;
  count: number;
}

export interface TurnTraceSettle {
  atMs: number;
  /** `resolved`, `resolved-undispatched`, or `rejected:<message>`. */
  outcome: string;
}

export interface TurnTraceSnapshot {
  /** The first and the last entries; consecutive events of one type are one entry. */
  events: TurnTraceEntry[];
  /** Entries between the kept first and last ones that were not retained. */
  dropped: number;
  settle: TurnTraceSettle | null;
}

export interface TurnTrace {
  recordEvent: (type: string) => void;
  recordSettle: (outcome: string) => void;
  snapshot: () => TurnTraceSnapshot;
}

/** Entries kept at each end of the record: the prelude and the ending are what a failed turn is judged by. */
const DEFAULT_KEPT_ENTRIES = 12;

export function createTurnTrace(now: () => number, keptEntries = DEFAULT_KEPT_ENTRIES): TurnTrace {
  const startedAt = now();
  const head: TurnTraceEntry[] = [];
  const tail: TurnTraceEntry[] = [];
  let dropped = 0;
  let settle: TurnTraceSettle | null = null;

  const newest = (): TurnTraceEntry | undefined => tail[tail.length - 1] ?? head[head.length - 1];

  return {
    recordEvent: (type) => {
      const at = now() - startedAt;
      const last = newest();
      if (last && last.type === type) {
        last.lastAtMs = at;
        last.count += 1;
        return;
      }
      const entry: TurnTraceEntry = { type, atMs: at, lastAtMs: at, count: 1 };
      if (tail.length === 0 && head.length < keptEntries) {
        head.push(entry);
        return;
      }
      tail.push(entry);
      if (tail.length > keptEntries) {
        tail.shift();
        dropped += 1;
      }
    },
    recordSettle: (outcome) => {
      if (settle === null) {
        settle = { atMs: now() - startedAt, outcome };
      }
    },
    snapshot: () => ({
      events: [...head, ...tail].map((entry) => ({ ...entry })),
      dropped,
      settle: settle === null ? null : { ...settle },
    }),
  };
}
