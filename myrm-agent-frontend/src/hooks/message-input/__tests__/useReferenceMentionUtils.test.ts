import { describe, expect, it, vi } from 'vitest';

const mockAgents = [
  { id: 'strategic-advisor', name: 'Strategic Advisor', description: 'Readonly strategy advisor', avatar_url: null },
  { id: 'code-reviewer', name: 'Code Reviewer', description: 'Code quality specialist', avatar_url: null },
];

vi.mock('@/store/useAgentStore', () => ({
  default: { getState: () => ({ agents: mockAgents }) },
}));

import { HISTORY_SEARCH_MAX_LENGTH } from '@/lib/constants/chat-history-search';
import { planMention } from '../useReferenceMentionUtils';

// A rare han character is one character to the server and two UTF-16 units to the browser.
const CHARACTER = '\u{20BB7}';

describe('planMention', () => {
  it('has no plan when the cursor is not inside a mention', () => {
    expect(planMention('hello world', 11, 'en', 'chat-1')).toBeNull();
    expect(planMention('mail me@example.com', 19, 'en', 'chat-1')).toBeNull();
    expect(planMention('@done ', 6, 'en', 'chat-1')).toBeNull();
  });

  it('shows the loaded agents and the matching commands at once and follows with a workspace search', () => {
    const plan = planMention('@code', 5, 'en', 'chat-1');

    expect(plan).toMatchObject({ rawQuery: 'code', start: 0, mode: 'plain', query: 'code', willSearch: true });
    expect(plan?.localResults.map((item) => item.label)).toEqual(['Code Reviewer']);
    expect(plan?.specialResults).toEqual([]);
  });

  it('offers every command after a bare @, and does not search a workspace that does not exist yet', () => {
    const plan = planMention('@', 1, 'en', undefined);

    expect(plan?.willSearch).toBe(false);
    expect(plan?.localResults.map((item) => item.label)).toEqual([
      'Strategic Advisor',
      'Code Reviewer',
      '@staged',
      '@diff',
      '@folder:',
      '@url:',
      '@wiki:',
      '@chat:',
    ]);
    expect(plan?.specialResults).toHaveLength(6);
  });

  it('drops the folder and wiki prefixes from the query and has no local suggestions for them', () => {
    expect(planMention('@folder:src', 11, 'en', 'chat-1')).toMatchObject({
      rawQuery: 'folder:src',
      mode: 'folder',
      query: 'src',
      localResults: [],
      willSearch: true,
    });
    expect(planMention('@wiki:rag', 9, 'en', 'chat-1')).toMatchObject({
      rawQuery: 'wiki:rag',
      mode: 'wiki',
      query: 'rag',
      localResults: [],
      willSearch: true,
    });
  });

  it('searches prior chats only once something follows @chat:, whether or not there is a workspace', () => {
    expect(planMention('@chat:', 6, 'en', undefined)).toMatchObject({ mode: 'chat', query: '', willSearch: false });
    expect(planMention('@chat:plan', 10, 'en', undefined)).toMatchObject({
      mode: 'chat',
      query: 'plan',
      willSearch: true,
    });
  });

  it('cuts a @chat: query to what the server accepts, counted in characters', () => {
    const text = `@chat:${CHARACTER.repeat(HISTORY_SEARCH_MAX_LENGTH + 5)}`;

    expect(planMention(text, text.length, 'en', 'chat-1')?.query).toBe(CHARACTER.repeat(HISTORY_SEARCH_MAX_LENGTH));
  });
});
