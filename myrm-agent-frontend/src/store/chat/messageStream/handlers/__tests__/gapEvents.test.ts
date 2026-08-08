import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType, type AgentStreamEvent } from '@/store/chat/types';
import { AdaptiveScheduler } from '../../../adaptiveScheduler';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';

const isLocalModeMock = vi.hoisted(() => vi.fn(() => false));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isLocalMode: () => isLocalModeMock(),
  };
});

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
    data: { type: eventType, data } as unknown as AgentStreamEvent,
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
    isLocalModeMock.mockReturnValue(false);
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

  it('ignores bare capability_gap without factual reason (enable-and-resend removed)', async () => {
    const result = await gapEvents(createCtx(AgentEventType.CAPABILITY_GAP, { tool_id: 'render_ui' }));
    expect(result).toBeNull();
    expect(toastInfo).not.toHaveBeenCalled();
    expect(setPendingGapRetry).not.toHaveBeenCalled();
  });

  it('ignores cron capability_gap without factual reason', async () => {
    document.documentElement.lang = 'zh';
    const result = await gapEvents(createCtx(AgentEventType.CAPABILITY_GAP, { tool_id: 'cron' }));
    expect(result).toBeNull();
    expect(toastInfo).not.toHaveBeenCalled();
    expect(setPendingGapRetry).not.toHaveBeenCalled();
  });

  it('shows info-only toast on surface_unavailable capability_gap', async () => {
    await gapEvents(
      createCtx(AgentEventType.CAPABILITY_GAP, {
        tool_id: 'render_ui',
        reason: 'surface_unavailable',
        display_message: 'Inline UI is Web-only.',
      }),
    );

    expect(toastInfo).toHaveBeenCalledWith('Inline UI is Web-only.', { duration: 12000 });
    expect(setPendingGapRetry).not.toHaveBeenCalled();
    const toastOptions = toastInfo.mock.calls[0]?.[1] as { action?: unknown };
    expect(toastOptions?.action).toBeUndefined();
  });

  it('uses localized fallback when surface_unavailable has no display_message', async () => {
    document.documentElement.lang = 'zh-CN';
    await gapEvents(
      createCtx(AgentEventType.CAPABILITY_GAP, {
        tool_id: 'render_ui',
        reason: 'surface_unavailable',
      }),
    );

    const toastMessage = toastInfo.mock.calls[0]?.[0] as string;
    expect(toastMessage).toContain('Web 对话');
    expect(setPendingGapRetry).not.toHaveBeenCalled();
  });

  it('shows settings CTA on web_search not_configured capability_gap', async () => {
    await gapEvents(
      createCtx(AgentEventType.CAPABILITY_GAP, {
        tool_id: 'web_search',
        reason: 'not_configured',
        display_message: 'Web search is enabled but no search API is configured.',
        settings_path: '/settings/search',
      }),
    );

    expect(toastInfo).toHaveBeenCalledTimes(1);
    expect(setPendingGapRetry).not.toHaveBeenCalled();
    const toastOptions = toastInfo.mock.calls[0]?.[1] as {
      action?: { label?: string; onClick?: () => void };
    };
    expect(toastOptions.action?.label).toBe('Go to Settings');
    expect(typeof toastOptions.action?.onClick).toBe('function');
  });

  it('shows settings CTA on migration_readiness_critical capability_gap', async () => {
    await gapEvents(
      createCtx(AgentEventType.CAPABILITY_GAP, {
        tool_id: 'migration_import',
        reason: 'migration_readiness_critical',
        display_message: 'Configure model providers in Settings.',
        settings_path: '/settings/models',
      }),
    );

    expect(toastInfo).toHaveBeenCalledTimes(1);
    expect(setPendingGapRetry).not.toHaveBeenCalled();
    const toastOptions = toastInfo.mock.calls[0]?.[1] as {
      action?: { label?: string; onClick?: () => void };
    };
    expect(toastOptions.action?.label).toBe('Go to Settings');
    expect(typeof toastOptions.action?.onClick).toBe('function');
  });

  it('shows settings CTA on migration_readiness_warning capability_gap', async () => {
    await gapEvents(
      createCtx(AgentEventType.CAPABILITY_GAP, {
        tool_id: 'migration_import',
        reason: 'migration_readiness_warning',
        display_message: 'Enable imported MCP servers in Settings.',
        settings_path: '/settings/mcp',
      }),
    );

    expect(toastInfo).toHaveBeenCalledTimes(1);
    const toastOptions = toastInfo.mock.calls[0]?.[1] as {
      action?: { label?: string; onClick?: () => void };
    };
    expect(toastOptions.action?.label).toBe('Go to Settings');
  });

  it('shows local quick-enable CTA on web_search not_configured in local mode', async () => {
    isLocalModeMock.mockReturnValue(true);
    document.documentElement.lang = 'zh';

    await gapEvents(
      createCtx(AgentEventType.CAPABILITY_GAP, {
        tool_id: 'web_search',
        reason: 'not_configured',
        display_message: '已开启网页搜索，但未配置搜索 API。',
        settings_path: '/settings/search',
      }),
    );

    const toastOptions = toastInfo.mock.calls[0]?.[1] as {
      action?: { label?: string };
    };
    expect(toastOptions.action?.label).toBe('一键启用免费搜索');
  });

  it('ignores capability_gap for agent baseline tool ids (no UI toggle)', async () => {
    const result = await gapEvents(
      createCtx(AgentEventType.CAPABILITY_GAP, { tool_id: 'file_ops' }),
    );
    expect(result).toBeNull();
    expect(toastInfo).not.toHaveBeenCalled();
    expect(setPendingGapRetry).not.toHaveBeenCalled();
  });

  it('ignores skill_gap events (bind-and-resend removed)', async () => {
    const result = await gapEvents(createCtx(AgentEventType.SKILL_GAP, { skill_id: 'github_pr_skill' }));
    expect(result).toBeNull();
    expect(setPendingGapRetry).not.toHaveBeenCalled();
    expect(toastInfo).not.toHaveBeenCalled();
  });
});
