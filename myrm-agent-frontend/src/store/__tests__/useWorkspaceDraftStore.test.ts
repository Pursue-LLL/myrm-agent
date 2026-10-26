/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { WorkspaceTextSnapshot } from '@/services/workspaceText';
import { keptDraft, latestDraftIn, useWorkspaceDraftStore } from '../useWorkspaceDraftStore';

const WORKSPACE = '/ws';
const A = '/ws/a.txt';
const B = '/ws/b.txt';

const base = (content = 'hello', version = 'v1'): WorkspaceTextSnapshot => ({
  path: A,
  name: 'a.txt',
  content,
  version,
  size: content.length,
  editable: true,
  readonlyReason: null,
  truncated: false,
});

const state = () => useWorkspaceDraftStore.getState();

/** What the browser does when the page is about to go: true when the user would be asked first. */
function leavingWouldAsk(): boolean {
  const event = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

beforeEach(() => {
  useWorkspaceDraftStore.setState({ drafts: {} });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('keeping and forgetting a draft', () => {
  it('keeps unsaved text with the version it started from, apart for every file and workspace', () => {
    const original = base();
    state().keep(WORKSPACE, A, original, 'hello!');

    expect(keptDraft(WORKSPACE, A)).toMatchObject({ workspace: WORKSPACE, path: A, text: 'hello!', base: original });
    expect(keptDraft(WORKSPACE, B)).toBeUndefined();
    expect(keptDraft('/other', A)).toBeUndefined();
  });

  it('replaces the text of a file and stamps the change', () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000);
    const original = base();
    state().keep(WORKSPACE, A, original, 'hello!');

    vi.setSystemTime(2_000);
    state().keep(WORKSPACE, A, original, 'hello!!');

    expect(keptDraft(WORKSPACE, A)).toMatchObject({ text: 'hello!!', editedAt: 2_000 });
    expect(Object.keys(state().drafts)).toHaveLength(1);
  });

  it('does nothing, and tells nobody, when asked to keep what it already holds', () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000);
    const original = base();
    state().keep(WORKSPACE, A, original, 'hello!');
    const listener = vi.fn();
    const unsubscribe = useWorkspaceDraftStore.subscribe(listener);

    vi.setSystemTime(5_000);
    state().keep(WORKSPACE, A, original, 'hello!');
    unsubscribe();

    expect(listener).not.toHaveBeenCalled();
    expect(keptDraft(WORKSPACE, A)?.editedAt).toBe(1_000);
  });

  it('forgets the draft of one file and leaves the others', () => {
    state().keep(WORKSPACE, A, base(), 'a!');
    state().keep(WORKSPACE, B, base(), 'b!');

    state().drop(WORKSPACE, A);

    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
    expect(keptDraft(WORKSPACE, B)?.text).toBe('b!');
  });

  it('tells nobody when the file had no draft to forget', () => {
    const listener = vi.fn();
    const unsubscribe = useWorkspaceDraftStore.subscribe(listener);

    state().drop(WORKSPACE, A);
    unsubscribe();

    expect(listener).not.toHaveBeenCalled();
  });

  it('moves a draft onto a newer version of the file without touching its text', () => {
    const older = base('hello', 'v1');
    const newer = base('hello', 'v2');
    state().keep(WORKSPACE, A, older, 'hello!');

    state().keep(WORKSPACE, A, newer, 'hello!');

    expect(keptDraft(WORKSPACE, A)?.base).toBe(newer);
  });

  it('never mixes up two files whose workspace and path read the same when put together', () => {
    state().keep('/a', 'b/c.txt', base(), 'first');
    state().keep('/ab', '/c.txt', base(), 'second');

    expect(keptDraft('/a', 'b/c.txt')?.text).toBe('first');
    expect(keptDraft('/ab', '/c.txt')?.text).toBe('second');
    expect(Object.keys(state().drafts)).toHaveLength(2);
  });
});

describe('a save that finished', () => {
  it('forgets the draft when the saved text is the kept text', () => {
    state().keep(WORKSPACE, A, base(), 'hello!');

    state().saved(WORKSPACE, A, 'hello!', { version: 'v2', size: 6 });

    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
  });

  it('lets text typed while the save ran continue from the version that was written', () => {
    state().keep(WORKSPACE, A, base(), 'hello!!');

    state().saved(WORKSPACE, A, 'hello!', { version: 'v2', size: 6 });

    expect(keptDraft(WORKSPACE, A)).toMatchObject({
      text: 'hello!!',
      base: { content: 'hello!', version: 'v2', size: 6, editable: true },
    });
  });

  it('has nothing to say about a file without a draft', () => {
    const listener = vi.fn();
    const unsubscribe = useWorkspaceDraftStore.subscribe(listener);

    state().saved(WORKSPACE, A, 'hello!', { version: 'v2', size: 6 });
    unsubscribe();

    expect(listener).not.toHaveBeenCalled();
    expect(state().drafts).toEqual({});
  });
});

describe('the draft a workspace reopens', () => {
  it('is the one edited last, among the drafts of that workspace only', () => {
    vi.useFakeTimers();
    const original = base();
    vi.setSystemTime(1_000);
    state().keep(WORKSPACE, A, original, 'a!');
    vi.setSystemTime(2_000);
    state().keep('/other', '/other/c.txt', original, 'c!');
    vi.setSystemTime(3_000);
    state().keep(WORKSPACE, B, original, 'b!');
    vi.setSystemTime(4_000);
    state().keep(WORKSPACE, A, original, 'a!!');

    expect(latestDraftIn(WORKSPACE)).toMatchObject({ path: A, text: 'a!!' });
    expect(latestDraftIn('/other')).toMatchObject({ path: '/other/c.txt' });
  });

  it('is nothing when the workspace has no draft', () => {
    state().keep('/other', '/other/c.txt', base(), 'c!');

    expect(latestDraftIn(WORKSPACE)).toBeUndefined();
  });
});

describe('leaving the page with drafts', () => {
  it('lets the page go without asking while nothing is unsaved', () => {
    expect(leavingWouldAsk()).toBe(false);
  });

  it('asks first while any draft exists, and stops asking once the last one is gone', () => {
    state().keep(WORKSPACE, A, base(), 'a!');
    state().keep(WORKSPACE, B, base(), 'b!');
    expect(leavingWouldAsk()).toBe(true);

    state().drop(WORKSPACE, A);
    expect(leavingWouldAsk()).toBe(true);

    state().saved(WORKSPACE, B, 'b!', { version: 'v2', size: 2 });
    expect(leavingWouldAsk()).toBe(false);
  });

  it('asks once however many times drafts change', () => {
    const add = vi.spyOn(window, 'addEventListener');
    const remove = vi.spyOn(window, 'removeEventListener');

    state().keep(WORKSPACE, A, base(), 'a!');
    state().keep(WORKSPACE, A, base(), 'a!!');
    state().keep(WORKSPACE, B, base(), 'b!');
    state().drop(WORKSPACE, A);
    state().drop(WORKSPACE, B);

    const listensFor = (calls: Array<[unknown, ...unknown[]]>) =>
      calls.filter(([type]) => String(type) === 'beforeunload');
    expect(listensFor(add.mock.calls)).toHaveLength(1);
    expect(listensFor(remove.mock.calls)).toHaveLength(1);
    add.mockRestore();
    remove.mockRestore();
  });

  it('cancels the unload and sets the return value that older browsers look for', () => {
    const add = vi.spyOn(window, 'addEventListener');
    state().keep(WORKSPACE, A, base(), 'a!');
    const registered = add.mock.calls.find(([type]) => String(type) === 'beforeunload')?.[1];
    add.mockRestore();
    const event = { preventDefault: vi.fn(), returnValue: undefined as string | undefined };

    expect(registered).toBeTypeOf('function');
    (registered as (event: unknown) => void)(event);

    expect(event.preventDefault).toHaveBeenCalledTimes(1);
    expect(event.returnValue).toBe('');
  });
});
