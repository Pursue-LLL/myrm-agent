/**
 * [INPUT]
 * - none (pure; the caller supplies the clock and, when a loss needs explaining, the call stack)
 *
 * [OUTPUT]
 * - createStoreTimeline: per-send record of how the chat store's message list changed (chat id, user/assistant
 *   message counts, loading flag), with the call stack of every change that lost user messages or switched chats
 * - condenseStack: a raw `Error.stack` reduced to `function@file:line` frames
 * - StoreTimeline / StoreTimelineSample / StoreTimelineEntry / StoreTimelineSnapshot
 *
 * [POS]
 * E2E bridge diagnostics. A turn whose assistant reply is streaming while the page holds no user message cannot be
 * explained by the final state alone; the sequence of states, and who wrote the one that lost the message, can.
 */

export interface StoreTimelineSample {
  chatId: string;
  /** Chat id the active workspace pane shows; differs from `chatId` when update routing could miss the store. */
  paneChatId: string;
  users: number;
  assistants: number;
  loading: boolean;
}

export interface StoreTimelineEntry extends StoreTimelineSample {
  /** Milliseconds after the timeline started. */
  atMs: number;
  /** Frames of the write that dropped user messages or changed the chat id, callee first. */
  stack?: string[];
}

export interface StoreTimelineSnapshot {
  /** The first and the last entries; a sample equal to the one before it is not an entry. */
  entries: StoreTimelineEntry[];
  /** Entries between the kept first and last ones that were not retained. */
  dropped: number;
}

export interface StoreTimeline {
  /** `captureStack` runs only for a change that lost user messages or switched chats. */
  observe: (sample: StoreTimelineSample, captureStack: () => string) => void;
  snapshot: () => StoreTimelineSnapshot;
}

/** Entries kept at each end: the prelude and the state the send ended in are what a failed turn is judged by. */
const DEFAULT_KEPT_ENTRIES = 12;
const DEFAULT_STACK_FRAMES = 8;

/** Frames of libraries and of this diagnostic say nothing about who wrote the store. */
const NOISE_FRAME_MARKERS = ['node_modules', 'e2eStoreTimeline'];

/**
 * A store write runs its listeners from inside `setState`, so the frames between the listener and the writer are
 * the store's own machinery. Dev-server chunks carry hashed names, so only the function name identifies them.
 */
const STORE_MACHINERY_WINDOW = 8;

interface StackFrame {
  name: string;
  path: string;
  line: string;
}

function parseFrame(line: string): StackFrame | null {
  const frame = /^\s*at\s+(.*)$/.exec(line);
  if (!frame) {
    return null;
  }
  const body = frame[1].replace(/^async\s+/, '').replace(/^new\s+/, '');
  const wrapped = /^(.*?)\s+\((.*)\)$/.exec(body);
  const position = /^(.*):(\d+):\d+$/.exec(wrapped ? wrapped[2] : body);
  if (!position || NOISE_FRAME_MARKERS.some((marker) => position[1].includes(marker))) {
    return null;
  }
  return { name: wrapped ? wrapped[1] : 'anonymous', path: position[1], line: position[2] };
}

const isStoreSetState = (frame: StackFrame): boolean => frame.name === 'setState' || frame.name.endsWith('.setState');

function dropStoreMachinery(frames: StackFrame[]): StackFrame[] {
  const lastSetState = frames.slice(0, STORE_MACHINERY_WINDOW).findLastIndex(isStoreSetState);
  return lastSetState === -1 ? frames : frames.slice(lastSetState + 1);
}

export function condenseStack(raw: string, limit = DEFAULT_STACK_FRAMES): string[] {
  const frames = raw.split('\n').flatMap((line) => parseFrame(line) ?? []);
  return dropStoreMachinery(frames)
    .slice(0, limit)
    .map((frame) => `${frame.name}@${frame.path.split('/').pop()?.replace(/\?.*$/, '') ?? ''}:${frame.line}`);
}

function isSameSample(a: StoreTimelineSample, b: StoreTimelineSample): boolean {
  return (
    a.chatId === b.chatId &&
    a.paneChatId === b.paneChatId &&
    a.users === b.users &&
    a.assistants === b.assistants &&
    a.loading === b.loading
  );
}

export function createStoreTimeline(now: () => number, keptEntries = DEFAULT_KEPT_ENTRIES): StoreTimeline {
  const startedAt = now();
  const head: StoreTimelineEntry[] = [];
  const tail: StoreTimelineEntry[] = [];
  let dropped = 0;

  const newest = (): StoreTimelineEntry | undefined => tail[tail.length - 1] ?? head[head.length - 1];

  return {
    observe: (sample, captureStack) => {
      const last = newest();
      if (last && isSameSample(last, sample)) {
        return;
      }
      const entry: StoreTimelineEntry = { atMs: now() - startedAt, ...sample };
      if (last && (sample.users < last.users || sample.chatId !== last.chatId)) {
        const stack = condenseStack(captureStack());
        if (stack.length > 0) {
          entry.stack = stack;
        }
      }
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
    snapshot: () => ({
      entries: [...head, ...tail].map((entry) => ({ ...entry, stack: entry.stack && [...entry.stack] })),
      dropped,
    }),
  };
}
