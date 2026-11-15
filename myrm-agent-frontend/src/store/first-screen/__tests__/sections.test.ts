import { describe, expect, it } from 'vitest';

import type { ChatItem } from '@/services/chat';
import type { Project } from '@/services/projects';
import {
  CHAT_HISTORY_SNAPSHOT_LIMIT,
  CHAT_PREVIEW_MAX_CHARS,
  chatHistoryFilterKey,
  decodeChatHistory,
  encodeChatHistory,
} from '../chatHistorySection';
import { decodeProjects, encodeProjects } from '../projectsSection';

const chat = (id: string, overrides: Partial<ChatItem> = {}): ChatItem => ({
  id,
  title: `Title ${id}`,
  firstMessage: 'a private first message',
  lastMessage: 'a private last message',
  actionMode: 'agent',
  source: 'cli',
  isCompacted: true,
  isPinned: true,
  pinOrder: 3,
  projectId: 'project-1',
  tags: ['work'],
  updatedAt: new Date('2026-11-14T08:00:00Z'),
  createdAt: new Date('2026-11-13T08:00:00Z'),
  ...overrides,
});

const project = (id: string, overrides: Partial<Project> = {}): Project => ({
  id,
  name: `Project ${id}`,
  description: 'about it',
  color: '#7cb9ff',
  sortOrder: 2,
  workspacePath: '/work/atlas',
  workspaceUsable: true,
  defaultAgentId: 'agent-1',
  goalSummary: 'ship it',
  createdAt: '2026-11-01T00:00:00Z',
  updatedAt: '2026-11-02T00:00:00Z',
  ...overrides,
});

const roundTrip = <T>(value: T): unknown => JSON.parse(JSON.stringify(value));

describe('chatHistoryFilterKey', () => {
  it('names the three lists the sidebar can show', () => {
    expect(chatHistoryFilterKey(undefined)).toBe('all');
    expect(chatHistoryFilterKey(null)).toBe('unassigned');
    expect(chatHistoryFilterKey('p1')).toBe('project:p1');
  });
});

describe('chat history section', () => {
  it('keeps what a row draws and gives the dates back as dates', () => {
    const decoded = decodeChatHistory(roundTrip(encodeChatHistory('all', [chat('a')])));

    expect(decoded?.filterKey).toBe('all');
    expect(decoded?.items).toEqual([{ ...chat('a'), firstMessage: '' }]);
    expect(decoded?.items[0].updatedAt).toBeInstanceOf(Date);
  });

  it('keeps the one-line preview a row draws and nothing else of the messages', () => {
    const stored = JSON.stringify(encodeChatHistory('all', [chat('a')]));

    expect(stored).toContain('a private last message');
    expect(stored).not.toContain('a private first message');
  });

  it('cuts a long preview to what the widest sidebar shows', () => {
    const decoded = decodeChatHistory(
      roundTrip(encodeChatHistory('all', [chat('a', { lastMessage: 'x'.repeat(400) })])),
    );

    expect(decoded?.items[0].lastMessage).toBe('x'.repeat(CHAT_PREVIEW_MAX_CHARS));
  });

  it('keeps an emoji whole when it ends inside the limit', () => {
    const preview = `${'a'.repeat(CHAT_PREVIEW_MAX_CHARS - 2)}\u{1F600}tail`;

    const decoded = decodeChatHistory(roundTrip(encodeChatHistory('all', [chat('a', { lastMessage: preview })])));

    expect(decoded?.items[0].lastMessage).toBe(`${'a'.repeat(CHAT_PREVIEW_MAX_CHARS - 2)}\u{1F600}`);
  });

  it('drops the lone half of an emoji the cut would leave at the end', () => {
    const preview = `${'a'.repeat(CHAT_PREVIEW_MAX_CHARS - 1)}\u{1F600}tail`;

    const decoded = decodeChatHistory(roundTrip(encodeChatHistory('all', [chat('a', { lastMessage: preview })])));

    expect(decoded?.items[0].lastMessage).toBe('a'.repeat(CHAT_PREVIEW_MAX_CHARS - 1));
  });

  it('gives a row stored without a preview an empty one', () => {
    const decoded = decodeChatHistory({
      filterKey: 'all',
      items: [{ id: 'a', title: 'Old', updatedAt: 1, createdAt: 1 }],
    });

    expect(decoded?.items[0].lastMessage).toBe('');
  });

  it('keeps one page of the list', () => {
    const many = Array.from({ length: CHAT_HISTORY_SNAPSHOT_LIMIT + 7 }, (_, index) => chat(`c${index}`));

    const decoded = decodeChatHistory(roundTrip(encodeChatHistory('all', many)));

    expect(decoded?.items).toHaveLength(CHAT_HISTORY_SNAPSHOT_LIMIT);
    expect(decoded?.items[0].id).toBe('c0');
  });

  it('fills what an older row lacks with the defaults the list service uses', () => {
    const decoded = decodeChatHistory({
      filterKey: 'all',
      items: [{ id: 'a', title: 'Only the basics', updatedAt: 1, createdAt: 1 }],
    });

    expect(decoded?.items[0]).toMatchObject({
      actionMode: 'fast',
      source: 'web',
      isCompacted: false,
      isPinned: false,
      pinOrder: 0,
      projectId: null,
      tags: [],
    });
  });

  it('drops a row that is not shaped like a chat and keeps the rest', () => {
    const decoded = decodeChatHistory({
      filterKey: 'all',
      items: [
        null,
        'text',
        { id: '', title: 'no id', updatedAt: 1, createdAt: 1 },
        { id: 'b', title: 7, updatedAt: 1, createdAt: 1 },
        { id: 'c', title: 'no dates' },
        { id: 'd', title: 'bad date', updatedAt: 'yesterday', createdAt: 1 },
        { id: 'ok', title: 'fine', updatedAt: 1, createdAt: 1, tags: ['x', 4, null] },
      ],
    });

    expect(decoded?.items.map((item) => item.id)).toEqual(['ok']);
    expect(decoded?.items[0].tags).toEqual(['x']);
  });

  it.each([null, undefined, 'text', [], { items: [] }, { filterKey: 'all' }, { filterKey: 1, items: [] }])(
    'rejects %j as a whole',
    (raw) => {
      expect(decodeChatHistory(raw)).toBeNull();
    },
  );
});

describe('stored data that is not what was written', () => {
  /** A deterministic generator of JSON-shaped junk: what a damaged or foreign storage entry could hold. */
  const junk = (seed: number): unknown => {
    let state = seed;
    const next = () => {
      state = (state * 1_103_515_245 + 12_345) % 2_147_483_648;
      return state / 2_147_483_648;
    };
    const build = (depth: number): unknown => {
      const pick = next();
      if (depth > 3 || pick < 0.3) {
        return [null, true, 0, -1, 1e308, 'text', '', 'x'.repeat(30)][Math.floor(next() * 8)];
      }
      if (pick < 0.6) {
        return Array.from({ length: Math.floor(next() * 4) }, () => build(depth + 1));
      }
      const keys = [
        'id',
        'title',
        'name',
        'items',
        'filterKey',
        'tags',
        'updatedAt',
        'createdAt',
        'lastMessage',
        'color',
      ];
      return Object.fromEntries(
        Array.from({ length: Math.floor(next() * 6) }, () => [
          keys[Math.floor(next() * keys.length)],
          build(depth + 1),
        ]),
      );
    };
    return build(0);
  };

  it('is never thrown on by either decoder', () => {
    for (let seed = 1; seed <= 2_000; seed += 1) {
      const value = junk(seed);
      expect(() => decodeChatHistory(value)).not.toThrow();
      expect(() => decodeProjects(value)).not.toThrow();
    }
  });
});

describe('projects section', () => {
  it('round-trips every field a project declares', () => {
    expect(decodeProjects(roundTrip(encodeProjects([project('p1'), project('p2')])))).toEqual([
      project('p1'),
      project('p2'),
    ]);
  });

  it('keeps the optional fields optional', () => {
    const bare = project('p1', {
      workspacePath: undefined,
      workspaceUsable: undefined,
      defaultAgentId: undefined,
    });

    const [decoded] = decodeProjects(roundTrip(encodeProjects([bare]))) ?? [];

    expect(decoded).not.toHaveProperty('workspacePath');
    expect(decoded).not.toHaveProperty('workspaceUsable');
    expect(decoded).not.toHaveProperty('defaultAgentId');
  });

  it('keeps an explicit "no default agent"', () => {
    const [decoded] = decodeProjects(roundTrip(encodeProjects([project('p1', { defaultAgentId: null })]))) ?? [];

    expect(decoded.defaultAgentId).toBeNull();
  });

  it('stores nothing the server sent beyond the declared fields', () => {
    const withExtras = { ...project('p1'), internalNote: 'do not keep' } as Project;

    expect(JSON.stringify(encodeProjects([withExtras]))).not.toContain('internalNote');
  });

  it('drops an entry that is not shaped like a project and keeps the rest', () => {
    const decoded = decodeProjects([null, 3, { id: '', name: 'x' }, { id: 'p', name: 4 }, { id: 'ok', name: 'Atlas' }]);

    expect(decoded?.map((item) => item.id)).toEqual(['ok']);
    expect(decoded?.[0]).toMatchObject({ name: 'Atlas', description: '', color: '', sortOrder: 0, goalSummary: '' });
    expect(decoded?.[0].createdAt).toBeNull();
  });

  it.each([null, undefined, 'text', {}, 7])('rejects %j as a whole', (raw) => {
    expect(decodeProjects(raw)).toBeNull();
  });
});
