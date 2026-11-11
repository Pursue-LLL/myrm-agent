import { describe, expect, it } from 'vitest';

import type { Source } from '@/store/chat/types';
import { sourceKind, sourceName } from '../sourceName';

/** The shapes the server really sends: a wiki hit has no title and no url, an MCP source only the skill and its calls. */
const KNOWLEDGE: Source = {
  index: 1,
  type: 'knowledge',
  kb_name: 'LLM-Wiki',
  filename: 'deploy-notes',
  section: 'Rollback',
  snippet: '…',
};
const MCP: Source = {
  index: 2,
  type: 'mcp',
  skill_name: 'github',
  calls: [{ tool_name: 'search', result_preview: '' }],
};
const CONVERSATION: Source = {
  index: 3,
  type: 'conversation_history',
  title: 'Planning the launch',
  conversation_id: 'c1',
};
const WEB: Source = { index: 4, type: 'web_search', title: 'Deploy guide', url: 'https://docs.example.com/guide' };

describe('sourceKind', () => {
  it.each([
    [KNOWLEDGE, 'knowledge'],
    [MCP, 'mcp'],
    [CONVERSATION, 'conversation'],
    [WEB, 'web'],
    [{ ...WEB, type: 'web_fetch' }, 'web'],
  ] as const)('tells %j apart as %s', (source, kind) => {
    expect(sourceKind(source)).toBe(kind);
  });

  it('goes by the name a source carries when its type is missing, so it still lands in its row', () => {
    expect(sourceKind({ kb_name: 'LLM-Wiki' })).toBe('knowledge');
    expect(sourceKind({ skill_name: 'github' })).toBe('mcp');
    expect(sourceKind({})).toBe('web');
  });
});

describe('sourceName', () => {
  it('names each kind by the field that carries its name', () => {
    expect(sourceName(KNOWLEDGE)).toBe('deploy-notes § Rollback');
    expect(sourceName({ ...KNOWLEDGE, section: undefined })).toBe('deploy-notes');
    expect(sourceName({ ...KNOWLEDGE, filename: undefined })).toBe('LLM-Wiki');
    expect(sourceName(MCP)).toBe('github');
    expect(sourceName(CONVERSATION)).toBe('Planning the launch');
    expect(sourceName(WEB)).toBe('Deploy guide');
  });

  it('words the section the way the caller does, and leaves it as it is when the caller does not', () => {
    const index = { ...KNOWLEDGE, section: 'index_routing' };

    expect(sourceName(index, (section) => (section === 'index_routing' ? 'Catalog index' : section))).toBe(
      'deploy-notes § Catalog index',
    );
    expect(sourceName(index)).toBe('deploy-notes § index_routing');
  });

  it('has no name for a source that carries none, so the caller picks its own stand-in', () => {
    const nameless: Source[] = [
      { index: 5, type: 'web_search', url: 'https://example.com' },
      { index: 6, type: 'mcp' },
      { index: 7, type: 'knowledge' },
      { index: 8, type: 'conversation_history' },
    ];

    expect(nameless.map((source) => sourceName(source))).toEqual([undefined, undefined, undefined, undefined]);
  });

  it('treats an empty field as no name, falling through to the next one that kind keeps', () => {
    expect(sourceName({ ...KNOWLEDGE, filename: '' })).toBe('LLM-Wiki');
    expect(sourceName({ ...KNOWLEDGE, filename: '', kb_name: '' })).toBeUndefined();
    expect(sourceName({ ...MCP, skill_name: '' })).toBeUndefined();
    expect(sourceName({ ...WEB, title: '' })).toBeUndefined();
  });
});
