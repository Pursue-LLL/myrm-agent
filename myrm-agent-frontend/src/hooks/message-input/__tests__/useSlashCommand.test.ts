import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const chatStoreRef = vi.hoisted(() => ({
  setInputMessage: vi.fn(),
  setPendingExplicitSkillActivation: vi.fn(),
  agentConfig: {
    selectedSkillIds: [] as string[],
    commandBindings: [] as unknown[],
  },
}));

const commandStoreRef = vi.hoisted(() => ({
  getAllItems: vi.fn(() => []),
  searchItems: vi.fn(() => []),
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

vi.mock('@/store/useChatStore', () => {
  const useChatStore = ((selector: (state: typeof chatStoreRef.state) => unknown) =>
    selector(chatStoreRef.state)) as unknown as {
    (selector: (state: typeof chatStoreRef.state) => unknown): unknown;
    getState: () => typeof chatStoreRef.state;
  };
  useChatStore.getState = () => chatStoreRef.state;
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
import type { SlashAction, SlashCommand } from '@/types/command';

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
    const input = '帮我写个周报 /周报';
    const { result } = renderHook(() => useSlashCommand(input, input.length));

    await act(async () => {
      await result.current.executeCommand(skillAction);
    });

    expect(chatStoreRef.setPendingExplicitSkillActivation).toHaveBeenCalledWith({
      skillNames: ['report_writer_skill'],
    });
    expect(chatStoreRef.setInputMessage).toHaveBeenCalledWith('帮我写个周报 ');
  });

  it('clears the input for a bare slash skill command', async () => {
    const { result } = renderHook(() => useSlashCommand('/周报', 3));

    await act(async () => {
      await result.current.executeCommand(skillAction);
    });

    expect(chatStoreRef.setInputMessage).toHaveBeenCalledWith('');
  });

  it('replaces a command template while preserving surrounding text', async () => {
    const command: SlashCommand = {
      id: 'cmd:write',
      name: 'write',
      type: 'command',
      template: '[use template]',
      createdAt: '2026-01-01T00:00:00Z',
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
});
