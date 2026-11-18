import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { KeyboardEvent } from 'react';

const chatStoreRef = vi.hoisted(() => ({
  setInputMessage: vi.fn(),
  setPendingExplicitSkillActivation: vi.fn(),
  agentConfig: {
    selectedSkillIds: [] as string[],
    commandBindings: [] as unknown[],
  },
}));

const commandStoreRef = vi.hoisted(() => ({
  getAllItems: vi.fn<() => SlashItem[]>(() => []),
  searchItems: vi.fn<(query: string) => SlashItem[]>(() => []),
  recordUsage: vi.fn(),
}));

const skillStoreRef = vi.hoisted(() => ({
  marketSkills: [] as unknown[],
  localSkills: [] as unknown[],
  fetchMarketSkills: vi.fn(async () => undefined),
  fetchLocalSkills: vi.fn(async () => undefined),
}));

const featureGateRef = vi.hoisted(() => ({
  isEnabled: vi.fn(() => false),
}));

const showToast = vi.hoisted(() => vi.fn());

vi.mock('@/services/i18nToastService', () => ({ showI18nToast: showToast }));

vi.mock('@/store/useChatStore', () => {
  const useChatStore = ((selector: (state: typeof chatStoreRef) => unknown) => selector(chatStoreRef)) as unknown as {
    (selector: (state: typeof chatStoreRef) => unknown): unknown;
    getState: () => typeof chatStoreRef;
  };
  useChatStore.getState = () => chatStoreRef;
  return { default: useChatStore };
});

vi.mock('@/store/useCommandStore', () => {
  const useCommandStore = () => commandStoreRef;
  useCommandStore.getState = () => commandStoreRef;
  return { useCommandStore };
});

vi.mock('@/store/skill', () => {
  const useSkillStore = ((selector: (state: typeof skillStoreRef) => unknown) =>
    selector(skillStoreRef)) as unknown as {
    (selector: (state: typeof skillStoreRef) => unknown): unknown;
    getState: () => typeof skillStoreRef;
  };
  useSkillStore.getState = () => skillStoreRef;
  return { useSkillStore };
});

vi.mock('@/store/useFeatureGateStore', () => {
  const useFeatureGateStore = ((selector: (state: typeof featureGateRef) => unknown) =>
    selector(featureGateRef)) as unknown as {
    (selector: (state: typeof featureGateRef) => unknown): unknown;
    getState: () => typeof featureGateRef;
  };
  useFeatureGateStore.getState = () => featureGateRef;
  return { useFeatureGateStore };
});

import { useSlashCommand } from '@/hooks/message-input/useSlashCommand';
import type { SlashAction, SlashCommand, SlashItem } from '@/types/command';

const skillAction: SlashAction = {
  id: 'skill:report_writer_skill',
  name: 'report_writer',
  description: 'Write reports',
  type: 'action',
  execute: async () => ({
    success: true,
    skillActivation: { skillNames: ['report_writer_skill'] },
  }),
};

describe('useSlashCommand', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatStoreRef.agentConfig = {
      selectedSkillIds: ['report_writer_skill'],
      commandBindings: [],
    };
  });

  it('opens the palette for a slash prefix', () => {
    const { result } = renderHook(() => useSlashCommand('/', 1));
    expect(result.current.showCommandPalette).toBe(true);
  });

  it('keeps the text prefix when a skill slash command is executed', async () => {
    const input = '帮我写个周报 /report';
    const { result } = renderHook(() => useSlashCommand(input, input.length));

    await act(async () => {
      await result.current.executeCommand(skillAction);
    });

    expect(chatStoreRef.setPendingExplicitSkillActivation).toHaveBeenCalledWith({
      skillNames: ['report_writer_skill'],
    });
    expect(chatStoreRef.setInputMessage).toHaveBeenCalledWith('帮我写个周报 ');
  });

  describe('when a command does not work', () => {
    const brokenAction = (execute: SlashAction['execute']): SlashAction => ({
      id: 'builtin:broken',
      name: 'broken',
      description: 'A command that fails',
      type: 'action',
      execute,
    });

    it('tells the user instead of leaving the composer silent when the command throws', async () => {
      const errorLog = vi.spyOn(console, 'error').mockImplementation(() => undefined);
      const { result } = renderHook(() => useSlashCommand('/broken', 7));

      await act(async () => {
        await result.current.executeCommand(
          brokenAction(async () => {
            throw new Error('boom');
          }),
        );
      });

      expect(showToast).toHaveBeenCalledWith('commands.executeFailed', undefined, { type: 'error' });
      expect(chatStoreRef.setInputMessage).not.toHaveBeenCalled();
      errorLog.mockRestore();
    });

    it('leaves the toast to a command that already reported its own failure', async () => {
      const errorLog = vi.spyOn(console, 'error').mockImplementation(() => undefined);
      const { result } = renderHook(() => useSlashCommand('/broken', 7));

      await act(async () => {
        await result.current.executeCommand(brokenAction(async () => ({ success: false, error: 'No active chat' })));
      });

      expect(showToast).not.toHaveBeenCalled();
      errorLog.mockRestore();
    });
  });

  it('clears the input for a bare slash skill command', async () => {
    const { result } = renderHook(() => useSlashCommand('/report', 7));

    await act(async () => {
      await result.current.executeCommand(skillAction);
    });

    expect(chatStoreRef.setInputMessage).toHaveBeenCalledWith('');
  });

  it('moves the highlight back to the first match when typing changes how many commands match', () => {
    const commandNamed = (name: string): SlashCommand => ({
      id: `cmd:${name}`,
      name,
      type: 'command',
      template: `/${name}`,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    });
    commandStoreRef.searchItems.mockImplementation((query) =>
      ['alpha', 'alpine', 'beta'].filter((name) => name.startsWith(query)).map(commandNamed),
    );
    const { result, rerender } = renderHook(({ input }) => useSlashCommand(input, input.length), {
      initialProps: { input: '/al' },
    });

    act(() => {
      result.current.handleKeyDown({ key: 'ArrowDown', preventDefault: vi.fn() } as unknown as KeyboardEvent);
    });
    expect(result.current.selectedIndex).toBe(1);

    rerender({ input: '/alph' });

    expect(result.current.filteredItems).toHaveLength(1);
    expect(result.current.selectedIndex).toBe(0);
  });

  it('accepts the active slash command with Tab key', async () => {
    const command: SlashCommand = {
      id: 'cmd:clear',
      name: 'clear',
      type: 'command',
      template: '/clear',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    };
    commandStoreRef.searchItems.mockReturnValue([command]);

    const input = '/cle';
    const { result } = renderHook(() => useSlashCommand(input, input.length));

    await act(async () => {
      result.current.handleKeyDown({
        key: 'Tab',
        preventDefault: vi.fn(),
      } as unknown as React.KeyboardEvent);
    });

    expect(chatStoreRef.setInputMessage).toHaveBeenCalledWith('/clear');
  });

  it('replaces a command template while preserving surrounding text', async () => {
    const command: SlashCommand = {
      id: 'cmd:write',
      name: 'write',
      type: 'command',
      template: '[use template]',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    };
    commandStoreRef.searchItems.mockReturnValue([command]);

    const input = '开始 /write';
    const { result } = renderHook(() => useSlashCommand(input, input.length));

    await act(async () => {
      await result.current.executeCommand(command);
    });

    expect(chatStoreRef.setInputMessage).toHaveBeenCalledWith('开始 [use template]');
    expect(commandStoreRef.recordUsage).toHaveBeenCalledWith('cmd:write');
  });

  it('keeps the text prefix when a skill slash command name contains a hyphen', async () => {
    const input = '帮我写周报 /weekly-report';
    const { result } = renderHook(() => useSlashCommand(input, input.length));

    await act(async () => {
      await result.current.executeCommand(skillAction);
    });

    expect(chatStoreRef.setPendingExplicitSkillActivation).toHaveBeenCalledWith({
      skillNames: ['report_writer_skill'],
    });
    expect(chatStoreRef.setInputMessage).toHaveBeenCalledWith('帮我写周报 ');
  });

  it('esc closes a hyphenated slash command', () => {
    const command: SlashCommand = {
      id: 'cmd:notes',
      name: 'my-notes',
      type: 'command',
      template: 'organize notes',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    };
    commandStoreRef.searchItems.mockReturnValue([command]);

    const input = '/weekly-report';
    const { result } = renderHook(() => useSlashCommand(input, input.length));

    act(() => {
      result.current.handleKeyDown({
        key: 'Escape',
        preventDefault: vi.fn(),
      } as unknown as KeyboardEvent);
    });

    expect(chatStoreRef.setInputMessage).toHaveBeenCalledWith('');
  });
});
