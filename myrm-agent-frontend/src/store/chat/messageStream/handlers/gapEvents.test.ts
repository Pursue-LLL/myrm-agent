import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import { AdaptiveScheduler } from '../../adaptiveScheduler';
import type { StreamHandlerActions, StreamHandlerState } from '../types';
import type { StreamCtx } from '../streamContext';
import { gapEvents } from './gapEvents';

const setCurrentBuiltinTools = vi.fn();
const updateAgentConfig = vi.fn();
const toastInfo = vi.fn();
const toastSuccess = vi.fn();

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: (...args: unknown[]) => toastInfo(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      currentBuiltinTools: ['web_search', 'memory'],
      agentConfig: { selectedSkillIds: ['bound_skill'] },
      setCurrentBuiltinTools,
      updateAgentConfig,
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
    setCurrentBuiltinTools.mockClear();
    updateAgentConfig.mockClear();
    toastInfo.mockClear();
    toastSuccess.mockClear();
  });

  it('enables builtin tool on capability_gap toast action', async () => {
    await gapEvents(createCtx(AgentEventType.CAPABILITY_GAP, { tool_id: 'browser' }));

    expect(toastInfo).toHaveBeenCalledTimes(1);
    const toastOptions = toastInfo.mock.calls[0]?.[1] as { action?: { onClick?: () => void } };
    toastOptions.action?.onClick?.();

    expect(setCurrentBuiltinTools).toHaveBeenCalledWith(['web_search', 'memory', 'browser']);
    expect(toastSuccess).toHaveBeenCalledTimes(1);
  });

  it('binds skill on skill_gap toast action', async () => {
    await gapEvents(createCtx(AgentEventType.SKILL_GAP, { skill_id: 'github_pr_skill' }));

    expect(toastInfo).toHaveBeenCalledTimes(1);
    const toastOptions = toastInfo.mock.calls[0]?.[1] as { action?: { onClick?: () => void } };
    toastOptions.action?.onClick?.();

    expect(updateAgentConfig).toHaveBeenCalledWith({
      selectedSkillIds: ['bound_skill', 'github_pr_skill'],
    });
    expect(toastSuccess).toHaveBeenCalledTimes(1);
  });
});
