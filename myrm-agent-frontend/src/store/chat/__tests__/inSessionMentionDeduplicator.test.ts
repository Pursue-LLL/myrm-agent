import { describe, expect, it, beforeEach } from 'vitest';
import { inSessionMentionDeduplicator } from '../inSessionMentionDeduplicator';
import type { MentionReference } from '@/store/chat/types';

describe('inSessionMentionDeduplicator', () => {
  const CHAT_A = 'chat-session-a';
  const CHAT_B = 'chat-session-b';

  beforeEach(() => {
    inSessionMentionDeduplicator.clearAll();
  });

  it('normalizes file paths correctly', () => {
    expect(inSessionMentionDeduplicator.normalizePath('src/foo.ts')).toBe('src/foo.ts');
    expect(inSessionMentionDeduplicator.normalizePath('/src/foo.ts')).toBe('src/foo.ts');
    expect(inSessionMentionDeduplicator.normalizePath('src\\bar\\baz.ts')).toBe('src/bar/baz.ts');
    expect(inSessionMentionDeduplicator.normalizePath('  //src/trimmed.ts  ')).toBe('src/trimmed.ts');
  });

  it('tracks injected paths per chat session', () => {
    expect(inSessionMentionDeduplicator.isPathInjected(CHAT_A, 'src/index.ts')).toBe(false);

    inSessionMentionDeduplicator.markInjected(CHAT_A, ['src/index.ts', '/lib/utils.ts'], 1);

    expect(inSessionMentionDeduplicator.isPathInjected(CHAT_A, 'src/index.ts')).toBe(true);
    expect(inSessionMentionDeduplicator.isPathInjected(CHAT_A, 'lib/utils.ts')).toBe(true);
    expect(inSessionMentionDeduplicator.getInjectedPaths(CHAT_A)).toEqual(['src/index.ts', '/lib/utils.ts']);

    // Chat B remains completely clean and isolated
    expect(inSessionMentionDeduplicator.isPathInjected(CHAT_B, 'src/index.ts')).toBe(false);
  });

  it('partitions fresh vs redundant mention references', () => {
    const fileRefA: MentionReference = {
      type: 'workspace_file',
      label: '@src/index.ts',
      path: 'src/index.ts',
      source: 'workspace',
      size: 1024,
    };
    const fileRefB: MentionReference = {
      type: 'workspace_file',
      label: '@lib/helper.ts',
      path: 'lib/helper.ts',
      source: 'workspace',
      size: 512,
    };
    const agentRef: MentionReference = {
      type: 'agent',
      label: '@General Assistant',
      source: 'special',
      size: null,
    };

    // First turn: both files are fresh
    const turn1 = inSessionMentionDeduplicator.partitionMentions(CHAT_A, [fileRefA, fileRefB, agentRef]);
    expect(turn1.fresh).toEqual([fileRefA, fileRefB, agentRef]);
    expect(turn1.redundant).toEqual([]);

    // Mark fileRefA as injected
    inSessionMentionDeduplicator.markInjected(CHAT_A, ['src/index.ts'], 1);

    // Second turn: fileRefA is redundant, fileRefB is fresh
    const turn2 = inSessionMentionDeduplicator.partitionMentions(CHAT_A, [fileRefA, fileRefB, agentRef]);
    expect(turn2.fresh).toEqual([fileRefB, agentRef]);
    expect(turn2.redundant).toEqual([fileRefA]);
  });

  it('clears session records cleanly', () => {
    inSessionMentionDeduplicator.markInjected(CHAT_A, ['src/main.ts'], 1);
    expect(inSessionMentionDeduplicator.isPathInjected(CHAT_A, 'src/main.ts')).toBe(true);

    inSessionMentionDeduplicator.clearSession(CHAT_A);
    expect(inSessionMentionDeduplicator.isPathInjected(CHAT_A, 'src/main.ts')).toBe(false);
  });
});
