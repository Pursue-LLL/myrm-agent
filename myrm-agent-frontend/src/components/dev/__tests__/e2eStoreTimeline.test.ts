import { describe, expect, it, vi } from 'vitest';

import { condenseStack, createStoreTimeline, type StoreTimelineSample } from '../e2eStoreTimeline';

function steppedClock(start: number): { now: () => number; at: (ms: number) => void } {
  let current = start;
  return {
    now: () => current,
    at: (ms: number) => {
      current = ms;
    },
  };
}

function sample(overrides: Partial<StoreTimelineSample> = {}): StoreTimelineSample {
  return { chatId: 'c-1', paneChatId: 'c-1', users: 0, assistants: 0, loading: false, ...overrides };
}

const NO_STACK = (): string => '';

describe('createStoreTimeline', () => {
  it('records the first sample as the baseline at time zero, without a stack', () => {
    const clock = steppedClock(1_000);
    const capture = vi.fn(NO_STACK);
    const timeline = createStoreTimeline(clock.now);

    timeline.observe(sample(), capture);

    expect(timeline.snapshot().entries).toEqual([{ atMs: 0, ...sample() }]);
    expect(capture).not.toHaveBeenCalled();
  });

  it('records a sample only when something it tracks changed', () => {
    const clock = steppedClock(0);
    const timeline = createStoreTimeline(clock.now);
    timeline.observe(sample(), NO_STACK);
    clock.at(200);
    timeline.observe(sample(), NO_STACK);
    clock.at(400);
    timeline.observe(sample({ loading: true }), NO_STACK);
    clock.at(600);
    timeline.observe(sample({ loading: true, users: 1 }), NO_STACK);

    expect(timeline.snapshot().entries.map((entry) => [entry.atMs, entry.loading, entry.users])).toEqual([
      [0, false, 0],
      [400, true, 0],
      [600, true, 1],
    ]);
  });

  it('captures a condensed stack when the user message count drops', () => {
    const clock = steppedClock(0);
    const timeline = createStoreTimeline(clock.now);
    timeline.observe(sample({ users: 1, assistants: 1 }), NO_STACK);
    clock.at(900);
    const capture = vi.fn(
      () => 'Error\n    at loadMessages (webpack-internal:///./src/store/chat/messageManagement.ts:132:35)',
    );
    timeline.observe(sample({ users: 0, assistants: 1 }), capture);

    expect(capture).toHaveBeenCalledTimes(1);
    expect(timeline.snapshot().entries[1]).toMatchObject({
      atMs: 900,
      users: 0,
      stack: ['loadMessages@messageManagement.ts:132'],
    });
  });

  it('captures a stack when the chat id changes', () => {
    const timeline = createStoreTimeline(() => 0);
    timeline.observe(sample({ users: 1 }), NO_STACK);
    const capture = vi.fn(() => 'Error\n    at initializeChat (http://localhost:3000/a/chatSessionInit.ts:59:7)');
    timeline.observe(sample({ chatId: 'c-2', users: 0 }), capture);

    expect(capture).toHaveBeenCalledTimes(1);
    expect(timeline.snapshot().entries[1].stack).toEqual(['initializeChat@chatSessionInit.ts:59']);
  });

  it('does not capture a stack for changes that are not a loss', () => {
    const timeline = createStoreTimeline(() => 0);
    const capture = vi.fn(NO_STACK);
    timeline.observe(sample(), capture);
    timeline.observe(sample({ users: 1 }), capture);
    timeline.observe(sample({ users: 1, assistants: 1, loading: true }), capture);
    timeline.observe(sample({ users: 1, assistants: 1, loading: false }), capture);
    timeline.observe(sample({ users: 1, assistants: 1, paneChatId: 'c-9' }), capture);

    expect(capture).not.toHaveBeenCalled();
    expect(timeline.snapshot().entries.every((entry) => entry.stack === undefined)).toBe(true);
  });

  it('keeps the first and the last entries and counts what it dropped', () => {
    const clock = steppedClock(0);
    const timeline = createStoreTimeline(clock.now, 2);
    for (let users = 0; users < 7; users += 1) {
      clock.at(users * 10);
      timeline.observe(sample({ users }), NO_STACK);
    }

    const snapshot = timeline.snapshot();
    expect(snapshot.entries.map((entry) => entry.users)).toEqual([0, 1, 5, 6]);
    expect(snapshot.dropped).toBe(3);
  });

  it('returns a snapshot that later samples do not change', () => {
    const timeline = createStoreTimeline(() => 0);
    timeline.observe(sample(), NO_STACK);
    const before = timeline.snapshot();
    timeline.observe(sample({ users: 1 }), NO_STACK);

    expect(before.entries).toHaveLength(1);
  });
});

describe('condenseStack', () => {
  it('keeps function name, file and line of each frame, callee first', () => {
    const raw = [
      'Error',
      '    at Object.setMessages (webpack-internal:///(app-pages-browser)/./src/store/useChatStore.ts:210:9)',
      '    at loadMessages (http://localhost:3000/_next/static/chunks/messageManagement.ts?v=3:132:35)',
      '    at http://localhost:3000/_next/static/chunks/app.js:88:12',
    ].join('\n');

    expect(condenseStack(raw)).toEqual([
      'Object.setMessages@useChatStore.ts:210',
      'loadMessages@messageManagement.ts:132',
      'anonymous@app.js:88',
    ]);
  });

  it('reads async and constructor frames and drops library and own frames', () => {
    const raw = [
      'Error',
      '    at observe (webpack-internal:///./src/components/dev/e2eStoreTimeline.ts:70:11)',
      '    at set (webpack-internal:///./node_modules/zustand/esm/vanilla.mjs:20:5)',
      '    at async maybeAttachToActiveTurn (webpack-internal:///./src/store/chat/messageManagement.ts:300:3)',
      '    at new Store (webpack-internal:///./src/store/x.ts:4:1)',
    ].join('\n');

    expect(condenseStack(raw)).toEqual(['maybeAttachToActiveTurn@messageManagement.ts:300', 'Store@x.ts:4']);
  });

  it('cuts the store write machinery so the stack starts at the writer', () => {
    // Shape of a real dev-server stack: the chunks of the store and of the library carry hashed names, so only
    // the function names tell the machinery (`setState`) from the writer (`setMessages` and its callers).
    const raw = [
      'Error',
      '    at http://localhost:14000/_next/static/chunks/20q2_1q8nogq._.js:22864:9',
      '    at setState (http://localhost:14000/_next/static/chunks/20q2_1q8nogq._.js:22864:9)',
      '    at store.setState (http://localhost:14000/_next/static/chunks/20q2_1q8nogq._.js:22784:5)',
      '    at Object.setMessages (http://localhost:14000/_next/static/chunks/store_0vs1bxq._.js:15858:3)',
      '    at initializeChat (http://localhost:14000/_next/static/chunks/store_0vs1bxq._.js:1661:7)',
      '    at attachToChat (http://localhost:14000/_next/static/chunks/dev_1kr5oga._.js:900:3)',
    ].join('\n');

    expect(condenseStack(raw)).toEqual([
      'Object.setMessages@store_0vs1bxq._.js:15858',
      'initializeChat@store_0vs1bxq._.js:1661',
      'attachToChat@dev_1kr5oga._.js:900',
    ]);
  });

  it('does not treat a deep setState frame as the store machinery', () => {
    const frames = [...'abcdefgh'].map((name, index) => `    at ${name} (http://h/${name}.ts:${index + 1}:1)`);
    const raw = ['Error', ...frames, '    at setState (http://h/s.ts:9:1)', '    at tail (http://h/t.ts:10:1)'].join(
      '\n',
    );

    expect(condenseStack(raw, 20)).toHaveLength(10);
  });

  it('limits the number of frames', () => {
    const frames = Array.from({ length: 20 }, (_, index) => `    at f${index} (http://h/a/file${index}.ts:${index}:1)`);

    expect(condenseStack(['Error', ...frames].join('\n'), 3)).toHaveLength(3);
  });

  it('returns nothing for an empty or unparsable stack', () => {
    expect(condenseStack('')).toEqual([]);
    expect(condenseStack('Error')).toEqual([]);
    expect(condenseStack('garbage without frames')).toEqual([]);
  });
});
