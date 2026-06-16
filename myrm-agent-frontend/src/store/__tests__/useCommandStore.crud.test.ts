import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { SlashAction, SlashCommand } from '@/types/command';

const syncSetMock = vi.fn();

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    set: syncSetMock,
    get: vi.fn(),
    initialize: vi.fn(),
    subscribe: vi.fn(),
  }),
}));

vi.mock('@/store/builtinActions', () => ({
  buildBuiltinActions: (): SlashAction[] => [
    {
      id: 'builtin:test',
      name: 'test',
      description: 'test action',
      type: 'action',
      execute: vi.fn(),
    },
  ],
}));

import { useCommandStore } from '@/store/useCommandStore';

describe('useCommandStore CRUD operations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCommandStore.setState({
      commands: [],
      recentCommandIds: [],
      isInitialized: true,
    });
  });

  describe('addCommand', () => {
    it('adds a new command with auto-generated fields', () => {
      useCommandStore.getState().addCommand({ name: 'greet', template: 'Hello!' });
      const cmds = useCommandStore.getState().commands;
      expect(cmds).toHaveLength(1);
      expect(cmds[0].name).toBe('greet');
      expect(cmds[0].template).toBe('Hello!');
      expect(cmds[0].type).toBe('command');
      expect(cmds[0].id).toMatch(/^cmd_/);
      expect(cmds[0].createdAt).toBeTruthy();
      expect(cmds[0].updatedAt).toBeTruthy();
    });

    it('syncs to ConfigSyncManager after add', () => {
      useCommandStore.getState().addCommand({ name: 'test', template: 'test' });
      expect(syncSetMock).toHaveBeenCalledWith('commands', expect.objectContaining({
        commands: expect.any(Array),
        recentCommandIds: expect.any(Array),
      }));
    });

    it('supports multiple commands', () => {
      useCommandStore.getState().addCommand({ name: 'a', template: 'A' });
      useCommandStore.getState().addCommand({ name: 'b', template: 'B' });
      expect(useCommandStore.getState().commands).toHaveLength(2);
    });
  });

  describe('updateCommand', () => {
    it('updates name and template', () => {
      useCommandStore.getState().addCommand({ name: 'old', template: 'Old template' });
      const id = useCommandStore.getState().commands[0].id;

      useCommandStore.getState().updateCommand(id, { name: 'new', template: 'New template' });
      const updated = useCommandStore.getState().commands[0];
      expect(updated.name).toBe('new');
      expect(updated.template).toBe('New template');
    });

    it('updates updatedAt timestamp', async () => {
      useCommandStore.getState().addCommand({ name: 'test', template: 'test' });
      const id = useCommandStore.getState().commands[0].id;
      const oldUpdated = useCommandStore.getState().commands[0].updatedAt;

      await new Promise((r) => setTimeout(r, 5));
      useCommandStore.getState().updateCommand(id, { name: 'renamed' });
      expect(useCommandStore.getState().commands[0].updatedAt).not.toBe(oldUpdated);
    });

    it('does nothing for non-existent id', () => {
      useCommandStore.getState().addCommand({ name: 'test', template: 'test' });
      useCommandStore.getState().updateCommand('non-existent', { name: 'x' });
      expect(useCommandStore.getState().commands[0].name).toBe('test');
    });

    it('syncs after update', () => {
      useCommandStore.getState().addCommand({ name: 'test', template: 'test' });
      syncSetMock.mockClear();
      const id = useCommandStore.getState().commands[0].id;
      useCommandStore.getState().updateCommand(id, { name: 'updated' });
      expect(syncSetMock).toHaveBeenCalled();
    });
  });

  describe('deleteCommand', () => {
    it('removes command by id', async () => {
      useCommandStore.getState().addCommand({ name: 'a', template: 'A' });
      await new Promise((r) => setTimeout(r, 5));
      useCommandStore.getState().addCommand({ name: 'b', template: 'B' });
      expect(useCommandStore.getState().commands).toHaveLength(2);
      const idA = useCommandStore.getState().commands[0].id;

      useCommandStore.getState().deleteCommand(idA);
      expect(useCommandStore.getState().commands).toHaveLength(1);
      expect(useCommandStore.getState().commands[0].name).toBe('b');
    });

    it('also removes from recentCommandIds', () => {
      useCommandStore.getState().addCommand({ name: 'test', template: 'test' });
      const id = useCommandStore.getState().commands[0].id;
      useCommandStore.getState().recordUsage(id);
      expect(useCommandStore.getState().recentCommandIds).toContain(id);

      useCommandStore.getState().deleteCommand(id);
      expect(useCommandStore.getState().recentCommandIds).not.toContain(id);
    });

    it('syncs after delete', () => {
      useCommandStore.getState().addCommand({ name: 'test', template: 'test' });
      syncSetMock.mockClear();
      const id = useCommandStore.getState().commands[0].id;
      useCommandStore.getState().deleteCommand(id);
      expect(syncSetMock).toHaveBeenCalled();
    });
  });

  describe('recordUsage', () => {
    it('adds id to front of recentCommandIds', () => {
      useCommandStore.getState().recordUsage('cmd_1');
      useCommandStore.getState().recordUsage('cmd_2');
      expect(useCommandStore.getState().recentCommandIds[0]).toBe('cmd_2');
      expect(useCommandStore.getState().recentCommandIds[1]).toBe('cmd_1');
    });

    it('deduplicates on re-record', () => {
      useCommandStore.getState().recordUsage('cmd_1');
      useCommandStore.getState().recordUsage('cmd_2');
      useCommandStore.getState().recordUsage('cmd_1');
      const recents = useCommandStore.getState().recentCommandIds;
      expect(recents[0]).toBe('cmd_1');
      expect(recents.filter((r) => r === 'cmd_1')).toHaveLength(1);
    });

    it('limits to 10 entries', () => {
      for (let i = 0; i < 15; i++) {
        useCommandStore.getState().recordUsage(`cmd_${i}`);
      }
      expect(useCommandStore.getState().recentCommandIds).toHaveLength(10);
    });

    it('syncs after record', () => {
      syncSetMock.mockClear();
      useCommandStore.getState().recordUsage('cmd_1');
      expect(syncSetMock).toHaveBeenCalled();
    });
  });

  describe('getAllItems', () => {
    it('returns actions followed by commands', () => {
      useCommandStore.getState().addCommand({ name: 'user-cmd', template: 'test' });
      const items = useCommandStore.getState().getAllItems();
      expect(items[0].type).toBe('action');
      expect(items[items.length - 1].type).toBe('command');
    });
  });
});
