import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { SlashAction, SlashCommand } from '@/types/command';

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    set: vi.fn(),
    get: vi.fn(),
    initialize: vi.fn(),
    subscribe: vi.fn(),
  }),
}));

vi.mock('@/store/builtinActions', () => ({
  buildBuiltinActions: (): SlashAction[] => [
    {
      id: 'builtin:compact',
      name: 'compact',
      description: 'commands.builtin.compact',
      argsHint: '[topic]',
      aliases: ['compress'],
      type: 'action',
      execute: vi.fn(),
    },
    {
      id: 'builtin:yolo',
      name: 'yolo',
      description: 'commands.builtin.yolo',
      argsHint: '[on|off|<seconds>]',
      type: 'action',
      execute: vi.fn(),
    },
    {
      id: 'builtin:freeze',
      name: 'freeze',
      description: 'commands.builtin.freeze',
      argsHint: '[off|resume]',
      aliases: ['estop'],
      type: 'action',
      execute: vi.fn(),
    },
  ],
}));

import { useCommandStore } from '@/store/useCommandStore';

describe('useCommandStore.searchItems', () => {
  beforeEach(() => {
    useCommandStore.setState({
      commands: [
        {
          id: 'cmd_1',
          name: 'greet',
          type: 'command',
          template: 'Hello, please help me with',
          createdAt: '2024-01-01',
          updatedAt: '2024-01-01',
        } satisfies SlashCommand,
        {
          id: 'cmd_2',
          name: 'debug',
          type: 'command',
          template: 'Debug the following error:',
          createdAt: '2024-01-01',
          updatedAt: '2024-01-01',
        } satisfies SlashCommand,
      ],
    });
  });

  it('matches action by name', () => {
    const results = useCommandStore.getState().searchItems('comp');
    const names = results.map((r) => r.name);
    expect(names).toContain('compact');
  });

  it('matches action by alias', () => {
    const results = useCommandStore.getState().searchItems('compress');
    const names = results.map((r) => r.name);
    expect(names).toContain('compact');
  });

  it('matches action by another alias', () => {
    const results = useCommandStore.getState().searchItems('estop');
    const names = results.map((r) => r.name);
    expect(names).toContain('freeze');
  });

  it('matches user command by name', () => {
    const results = useCommandStore.getState().searchItems('greet');
    const names = results.map((r) => r.name);
    expect(names).toContain('greet');
  });

  it('matches user command by template content', () => {
    const results = useCommandStore.getState().searchItems('error');
    const names = results.map((r) => r.name);
    expect(names).toContain('debug');
  });

  it('search is case-insensitive', () => {
    const results = useCommandStore.getState().searchItems('COMPACT');
    const names = results.map((r) => r.name);
    expect(names).toContain('compact');
  });

  it('returns empty array for no match', () => {
    const results = useCommandStore.getState().searchItems('zzzznonexistent');
    expect(results).toHaveLength(0);
  });

  it('returns all items for empty getAllItems call', () => {
    const all = useCommandStore.getState().getAllItems();
    expect(all.length).toBe(5); // 3 actions + 2 commands
  });

  it('matches action by description (i18n key)', () => {
    const results = useCommandStore.getState().searchItems('commands.builtin');
    expect(results.length).toBeGreaterThan(0);
    expect(results.every((r) => r.type === 'action')).toBe(true);
  });

  it('does not match command by action-only fields', () => {
    const results = useCommandStore.getState().searchItems('compress');
    const hasCommand = results.some((r) => r.type === 'command');
    expect(hasCommand).toBe(false);
  });

  it('handles special characters in query without error', () => {
    expect(() => useCommandStore.getState().searchItems('.*+?')).not.toThrow();
  });

  it('handles empty string query gracefully', () => {
    const results = useCommandStore.getState().searchItems('');
    expect(results.length).toBe(5); // everything matches empty
  });

  it('partial alias match works', () => {
    const results = useCommandStore.getState().searchItems('esto');
    const names = results.map((r) => r.name);
    expect(names).toContain('freeze');
  });
});
