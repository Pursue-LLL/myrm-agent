import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import { AdaptiveScheduler } from '../../../adaptiveScheduler';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { gapEvents } from '../gapEvents';

const setCurrentBuiltinTools = vi.fn();
const setPendingGapRetry = vi.fn((pending) => {
  mockState.pendingGapRetry = pending;
});
const updateAgentConfig = vi.fn((partial: { selectedSkillIds?: string[] }) => {
  mockState.agentConfig = {
    selectedSkillIds: partial.selectedSkillIds ?? mockState.agentConfig.selectedSkillIds,
  };
});
const sendMessage = vi.fn().mockResolvedValue(undefined);
const clearPendingGapRetry = vi.fn(() => {
  mockState.pendingGapRetry = null;
});
const toastInfo = vi.fn();
const toastSuccess = vi.fn();

let mockLoading = false;
let mockState = {
  pendingGapRetry: null as
    | { kind: 'capability'; text: string; toolId: string }
    | { kind: 'skill'; text: string; skillId: string }
    | null,
  currentBuiltinTools: ['web_search', 'memory'] as string[],
  agentConfig: { selectedSkillIds: ['bound_skill'] as string[] },
  loading: false,
  messages: [{ role: 'user', content: '帮我填表准备 staging 部署配置' }],
};

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: (...args: unknown[]) => toastInfo(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      ...mockState,
      loading: mockLoading,
      setCurrentBuiltinTools: (tools: string[]) => {
        mockState.currentBuiltinTools = tools;
        setCurrentBuiltinTools(tools);
      },
      setPendingGapRetry,
      updateAgentConfig,
      sendMessage,
      clearPendingGapRetry,
    }),
  },
}));

function createCtx(eventType: string, data: Record<string, string>): StreamCtx {
  const state: StreamHandlerState = {
    messages: [],
    messageAppeared: false,
    loading: true,
    scheduler: new AdaptiveScheduler(),
  };
  const actions: StreamHandlerActions = {
    setMessages: (updater) => updater(state),
    setMessageAppeared: () => undefined,
    setLoading: () => undefined,
    _processSuggestions: async () => undefined,
    scheduleAutoSave: () => undefined,
  };

  return {
    data: { type: eventType, data },
    input: '',
    sources: undefined,
    added: false,
    recievedMessage: '',
    state,
    actions,
    files: [],
  };
}

describe('gapEvents', () => {
  beforeEach(() => {
    document.documentElement.lang = 'en';
    mockLoading = false;
    mockState = {
      pendingGapRetry: null,
      currentBuiltinTools: ['web_search', 'memory'],
      agentConfig: { selectedSkillIds: ['bound_skill'] },
      loading: false,
      messages: [{ role: 'user', content: '帮我填表准备 staging 部署配置' }],
    };
    setCurrentBuiltinTools.mockClear();
    setPendingGapRetry.mockClear();
    updateAgentConfig.mockClear();
    sendMessage.mockClear();
    toastInfo.mockClear();
    toastSuccess.mockClear();
  });

  it('stores pending retry on capability_gap', async () => {
    await gapEvents(createCtx(AgentEventType.CAPABILITY_GAP, { tool_id: 'render_ui' }));

    expect(setPendingGapRetry).toHaveBeenCalledWith({
      kind: 'capability',
      text: '帮我填表准备 staging 部署配置',
      toolId: 'render_ui',
    });
  });

  it('enables builtin tool and resends last user message on capability_gap toast action', async () => {
    await gapEvents(createCtx(AgentEventType.CAPABILITY_GAP, { tool_id: 'render_ui' }));

    expect(toastInfo).toHaveBeenCalledTimes(1);
    const toastOptions = toastInfo.mock.calls[0]?.[1] as { action?: { onClick?: () => Promise<void> } };
    await toastOptions.action?.onClick?.();
    expect(setCurrentBuiltinTools).toHaveBeenCalledWith(['web_search', 'memory', 'render_ui']);
    expect(sendMessage).toHaveBeenCalledWith(
      '帮我填表准备 staging 部署配置',
      expect.any(String),
    );
    expect(toastSuccess).toHaveBeenCalledWith('Enabled and resent your request.');
  });

  it('defers resend while loading and shows deferred toast', async () => {
    mockLoading = true;
    await gapEvents(createCtx(AgentEventType.CAPABILITY_GAP, { tool_id: 'render_ui' }));

    const toastOptions = toastInfo.mock.calls[0]?.[1] as { action?: { onClick?: () => Promise<void> } };
    await toastOptions.action?.onClick?.();

    expect(setCurrentBuiltinTools).toHaveBeenCalledWith(['web_search', 'memory', 'render_ui']);
    expect(sendMessage).not.toHaveBeenCalled();
    expect(toastSuccess).toHaveBeenCalledWith('Enabled. Will resend after this turn finishes.');
  });

  it('shows cron scheduled-task label on capability_gap toast', async () => {
    document.documentElement.lang = 'zh';
    await gapEvents(createCtx(AgentEventType.CAPABILITY_GAP, { tool_id: 'cron' }));

    expect(toastInfo).toHaveBeenCalledTimes(1);
    const toastMessage = toastInfo.mock.calls[0]?.[0] as string;
    expect(toastMessage).toContain('定时任务');
    const toastOptions = toastInfo.mock.calls[0]?.[1] as { action?: { label?: string; onClick?: () => Promise<void> } };
    expect(toastOptions.action?.label).toBe('开启并重发');
    await toastOptions.action?.onClick?.();
    expect(setCurrentBuiltinTools).toHaveBeenCalledWith(['web_search', 'memory', 'cron']);
  });

  it('ignores capability_gap for agent baseline tool ids (no UI toggle)', async () => {
    const result = await gapEvents(
      createCtx(AgentEventType.CAPABILITY_GAP, { tool_id: 'file_ops' }),
    );
    expect(result).toBeNull();
    expect(toastInfo).not.toHaveBeenCalled();
    expect(setPendingGapRetry).not.toHaveBeenCalled();
  });

  it('binds skill and resends last user message on skill_gap toast action', async () => {
    await gapEvents(createCtx(AgentEventType.SKILL_GAP, { skill_id: 'github_pr_skill' }));

    expect(setPendingGapRetry).toHaveBeenCalledWith({
      kind: 'skill',
      text: '帮我填表准备 staging 部署配置',
      skillId: 'github_pr_skill',
    });
    expect(toastInfo).toHaveBeenCalledTimes(1);
    const toastOptions = toastInfo.mock.calls[0]?.[1] as { action?: { onClick?: () => Promise<void> } };
    await toastOptions.action?.onClick?.();
    expect(updateAgentConfig).toHaveBeenCalledWith({
      selectedSkillIds: ['bound_skill', 'github_pr_skill'],
    });
    expect(sendMessage).toHaveBeenCalledWith(
      '帮我填表准备 staging 部署配置',
      expect.any(String),
    );
    expect(toastSuccess).toHaveBeenCalledWith('Skill bound and resent your request.');
  });
});
