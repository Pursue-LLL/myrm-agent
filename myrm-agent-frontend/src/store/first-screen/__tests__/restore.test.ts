import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatItem } from '@/services/chat';
import type { Project } from '@/services/projects';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';

const runtime = vi.hoisted(() => ({ enabled: true, backendReady: false }));

vi.mock('../gate', () => ({ isFirstScreenSnapshotEnabled: () => runtime.enabled }));
vi.mock('@/lib/platform-readiness', () => ({
  getPlatformReadinessSnapshot: () => ({
    state: runtime.backendReady ? 'ready' : 'warming',
    database: runtime.backendReady,
  }),
}));

import { encodeChatHistory } from '../chatHistorySection';
import { flushSnapshot, resetSnapshotForTests, writeSnapshotSection } from '../envelope';
import { encodeProjects } from '../projectsSection';
import { resetSeedingForTests, seedChatHistoryFromSnapshot, seedProjectsFromSnapshot } from '../restore';

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

const store = (section: 'chatHistory' | 'projects', data: unknown) => {
  writeSnapshotSection(section, data);
  flushSnapshot();
};
const ids = () => useChatStore.getState().chatHistoryItems.map((item) => item.id);

beforeEach(() => {
  window.localStorage.clear();
  resetSnapshotForTests();
  resetSeedingForTests();
  runtime.enabled = true;
  runtime.backendReady = false;
  useChatStore.setState({
    chatHistoryItems: [],
    chatHistoryPagination: null,
    chatHistoryLoading: false,
    chatHistoryError: 'earlier failure',
  });
  useProjectStore.setState({ projects: [], activeFilter: undefined, loaded: false });
});

afterEach(() => {
  resetSnapshotForTests();
});

describe('seedChatHistoryFromSnapshot', () => {
  it('puts the stored list into the chat store without claiming the server confirmed it', () => {
    store('chatHistory', encodeChatHistory('all', [chat('a'), chat('b')]));

    expect(seedChatHistoryFromSnapshot(undefined)).toBe(true);

    const state = useChatStore.getState();
    expect(ids()).toEqual(['a', 'b']);
    expect(state.chatHistoryPagination).toBeNull();
    expect(state.chatHistoryLoading).toBe(false);
    expect(state.chatHistoryError).toBeNull();
  });

  it('offers the stored list to the first mount only', () => {
    store('chatHistory', encodeChatHistory('all', [chat('a')]));

    expect(seedChatHistoryFromSnapshot(undefined)).toBe(true);
    useChatStore.setState({ chatHistoryItems: [] });

    expect(seedChatHistoryFromSnapshot(undefined)).toBe(false);
    expect(ids()).toEqual([]);
  });

  it('uses the list of the project filter the window starts with, and no other', () => {
    store('chatHistory', encodeChatHistory('project:p1', [chat('a')]));

    expect(seedChatHistoryFromSnapshot(undefined)).toBe(false);
    expect(ids()).toEqual([]);
  });

  it('seeds a project-filtered list when the filter matches', () => {
    store('chatHistory', encodeChatHistory('project:p1', [chat('a')]));

    expect(seedChatHistoryFromSnapshot('p1')).toBe(true);
    expect(ids()).toEqual(['a']);
  });

  it('seeds nothing when the feature is off', () => {
    store('chatHistory', encodeChatHistory('all', [chat('a')]));
    runtime.enabled = false;

    expect(seedChatHistoryFromSnapshot(undefined)).toBe(false);
    expect(ids()).toEqual([]);
  });

  it('seeds nothing when the backend already answers', () => {
    store('chatHistory', encodeChatHistory('all', [chat('a')]));
    runtime.backendReady = true;

    expect(seedChatHistoryFromSnapshot(undefined)).toBe(false);
  });

  it('seeds nothing from an empty list, a missing section or garbage', () => {
    expect(seedChatHistoryFromSnapshot(undefined)).toBe(false);

    resetSeedingForTests();
    store('chatHistory', encodeChatHistory('all', []));
    expect(seedChatHistoryFromSnapshot(undefined)).toBe(false);

    resetSeedingForTests();
    store('chatHistory', { filterKey: 'all', items: 'nope' });
    expect(seedChatHistoryFromSnapshot(undefined)).toBe(false);
  });

  it('keeps the error of a failed earlier read when there is nothing to seed', () => {
    seedChatHistoryFromSnapshot(undefined);

    expect(useChatStore.getState().chatHistoryError).toBe('earlier failure');
  });
});

describe('seedProjectsFromSnapshot', () => {
  it('puts the stored projects in and leaves the store marked as not fetched', () => {
    store('projects', encodeProjects([project('p1'), project('p2')]));

    seedProjectsFromSnapshot();

    const state = useProjectStore.getState();
    expect(state.projects.map((item) => item.id)).toEqual(['p1', 'p2']);
    expect(state.loaded).toBe(false);
  });

  it('offers the stored projects to the first mount only', () => {
    store('projects', encodeProjects([project('p1')]));

    seedProjectsFromSnapshot();
    useProjectStore.setState({ projects: [] });
    seedProjectsFromSnapshot();

    expect(useProjectStore.getState().projects).toEqual([]);
  });

  it('never replaces projects that were fetched or are already there', () => {
    store('projects', encodeProjects([project('stored')]));
    useProjectStore.setState({ projects: [project('fetched')], loaded: true });

    seedProjectsFromSnapshot();
    expect(useProjectStore.getState().projects.map((item) => item.id)).toEqual(['fetched']);

    resetSeedingForTests();
    useProjectStore.setState({ projects: [project('typed')], loaded: false });
    seedProjectsFromSnapshot();
    expect(useProjectStore.getState().projects.map((item) => item.id)).toEqual(['typed']);
  });

  it('seeds nothing when the feature is off', () => {
    store('projects', encodeProjects([project('p1')]));
    runtime.enabled = false;

    seedProjectsFromSnapshot();

    expect(useProjectStore.getState().projects).toEqual([]);
  });
});
