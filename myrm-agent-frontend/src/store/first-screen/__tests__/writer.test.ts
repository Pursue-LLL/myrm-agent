import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatItem, PaginationInfo } from '@/services/chat';
import type { Project } from '@/services/projects';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';

const runtime = vi.hoisted(() => ({ enabled: true }));

vi.mock('../gate', () => ({ isFirstScreenSnapshotEnabled: () => runtime.enabled }));

import { decodeChatHistory } from '../chatHistorySection';
import { readSnapshotSection, resetSnapshotForTests } from '../envelope';
import { decodeProjects } from '../projectsSection';
import { startFirstScreenSnapshotWriter } from '../writer';

const chat = (id: string): ChatItem => ({
  id,
  title: `Title ${id}`,
  firstMessage: '',
  lastMessage: '',
  actionMode: 'agent',
  source: 'web',
  updatedAt: new Date('2026-11-14T08:00:00Z'),
  createdAt: new Date('2026-11-13T08:00:00Z'),
});

const project = (id: string): Project => ({
  id,
  name: `Project ${id}`,
  description: '',
  color: '#7cb9ff',
  sortOrder: 0,
  goalSummary: '',
  createdAt: null,
  updatedAt: null,
});

const pagination = (): PaginationInfo => ({
  page: 1,
  page_size: 20,
  total: 1,
  total_pages: 1,
  has_next: false,
  has_prev: false,
});

/** The state the store is in after the server answered a first page. */
const confirm = (items: ChatItem[]) =>
  useChatStore.setState({
    chatHistoryItems: items,
    chatHistoryPagination: pagination(),
    chatHistoryLoading: false,
    chatHistoryError: null,
  });

const settle = () => vi.advanceTimersByTime(1_000);
const storedChat = () => decodeChatHistory(readSnapshotSection('chatHistory'));
const storedProjects = () => decodeProjects(readSnapshotSection('projects'));

let stop: () => void = () => undefined;

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
  resetSnapshotForTests();
  runtime.enabled = true;
  useChatStore.setState({
    chatHistoryItems: [],
    chatHistoryPagination: null,
    chatHistoryLoading: false,
    chatHistoryError: null,
    chatHistorySourceFilter: null,
    chatHistorySearchKeyword: '',
    inputMessage: '',
  });
  useProjectStore.setState({ projects: [], activeFilter: undefined, loaded: false });
});

afterEach(() => {
  stop();
  stop = () => undefined;
  resetSnapshotForTests();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('chat history', () => {
  it('stores the list the server confirmed, under the list it belongs to', () => {
    stop = startFirstScreenSnapshotWriter();

    confirm([chat('a'), chat('b')]);
    settle();

    expect(storedChat()?.filterKey).toBe('all');
    expect(storedChat()?.items.map((item) => item.id)).toEqual(['a', 'b']);
  });

  it('keys the stored list by the project filter in force', () => {
    useProjectStore.setState({ activeFilter: 'p1' });
    stop = startFirstScreenSnapshotWriter();

    confirm([chat('a')]);
    settle();

    expect(storedChat()?.filterKey).toBe('project:p1');
  });

  it('follows later changes to the confirmed list, such as a new chat', () => {
    stop = startFirstScreenSnapshotWriter();
    confirm([chat('a')]);
    settle();

    useChatStore.setState({ chatHistoryItems: [chat('new'), chat('a')] });
    settle();

    expect(storedChat()?.items.map((item) => item.id)).toEqual(['new', 'a']);
  });

  it('stores a confirmed list the stores already hold when it starts', () => {
    confirm([chat('a')]);

    stop = startFirstScreenSnapshotWriter();
    settle();

    expect(storedChat()?.items.map((item) => item.id)).toEqual(['a']);
  });

  it.each([
    ['a list restored from a snapshot (no pagination from the server)', { chatHistoryPagination: null }],
    ['a list that is being read again', { chatHistoryLoading: true }],
    ['a list whose last read failed', { chatHistoryError: 'backend down' }],
    ['a list narrowed to one source', { chatHistorySourceFilter: 'cli' }],
    ['a list narrowed by a search keyword', { chatHistorySearchKeyword: ' plan ' }],
  ])('does not store %s', (_label, deviation) => {
    stop = startFirstScreenSnapshotWriter();

    useChatStore.setState({
      chatHistoryItems: [chat('a')],
      chatHistoryPagination: pagination(),
      chatHistoryLoading: false,
      chatHistoryError: null,
      ...deviation,
    });
    settle();

    expect(storedChat()).toBeNull();
  });

  it('keeps its own failure away from the store update it rides on', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    stop = startFirstScreenSnapshotWriter();
    const damaged = { ...chat('a'), updatedAt: 'not a date' } as unknown as ChatItem;

    expect(() => confirm([damaged])).not.toThrow();

    expect(useChatStore.getState().chatHistoryItems).toEqual([damaged]);
    expect(warn).toHaveBeenCalledOnce();
    expect(storedChat()).toBeNull();
  });

  it('does not write when something unrelated to the list changes', () => {
    stop = startFirstScreenSnapshotWriter();
    confirm([chat('a')]);
    settle();
    const setItem = vi.spyOn(Storage.prototype, 'setItem');

    for (let keystroke = 1; keystroke <= 20; keystroke += 1) {
      useChatStore.setState({ inputMessage: 'x'.repeat(keystroke) });
    }
    settle();

    expect(setItem).not.toHaveBeenCalled();
  });
});

describe('projects', () => {
  it('stores the projects once they are fetched and not before', () => {
    stop = startFirstScreenSnapshotWriter();

    useProjectStore.setState({ projects: [project('typed')] });
    settle();
    expect(storedProjects()).toBeNull();

    useProjectStore.setState({ projects: [project('p1'), project('p2')], loaded: true });
    settle();
    expect(storedProjects()?.map((item) => item.id)).toEqual(['p1', 'p2']);
  });

  it('follows a project added later', () => {
    stop = startFirstScreenSnapshotWriter();
    useProjectStore.setState({ projects: [project('p1')], loaded: true });
    settle();

    useProjectStore.setState({ projects: [project('p1'), project('p2')] });
    settle();

    expect(storedProjects()?.map((item) => item.id)).toEqual(['p1', 'p2']);
  });
});

describe('lifecycle', () => {
  it('writes at once when the page is hidden for good', () => {
    stop = startFirstScreenSnapshotWriter();
    confirm([chat('a')]);

    window.dispatchEvent(new Event('pagehide'));

    expect(storedChat()?.items).toHaveLength(1);
  });

  it('writes at once when the window goes to the background, not when it comes back', () => {
    stop = startFirstScreenSnapshotWriter();
    confirm([chat('a')]);
    const visibility = vi.spyOn(document, 'visibilityState', 'get');

    visibility.mockReturnValue('visible');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(storedChat()).toBeNull();

    visibility.mockReturnValue('hidden');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(storedChat()?.items).toHaveLength(1);
  });

  it('flushes what is pending and stops listening when it is stopped', () => {
    const stopWriter = startFirstScreenSnapshotWriter();
    confirm([chat('a')]);

    stopWriter();
    expect(storedChat()?.items).toHaveLength(1);

    confirm([chat('a'), chat('later')]);
    settle();
    expect(storedChat()?.items).toHaveLength(1);
  });

  it('does nothing where the snapshot is not used', () => {
    runtime.enabled = false;

    stop = startFirstScreenSnapshotWriter();
    confirm([chat('a')]);
    useProjectStore.setState({ projects: [project('p1')], loaded: true });
    window.dispatchEvent(new Event('pagehide'));
    settle();

    expect(storedChat()).toBeNull();
    expect(storedProjects()).toBeNull();
  });
});
