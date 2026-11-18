import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  buildChatState,
  chatStoreRef,
  mockEnqueue,
  mockQueuePendingChatWikiQuerySuccess,
  mockRecordChatWikiQueryAttempt,
  mockRecordChatWikiQuerySubmitted,
  mockRecordTurnCapabilityBusyRequeued,
  mockRecordTurnCapabilityOverrideApplied,
  mockRecordTurnCapabilityOverrideNoop,
  mockRecordTurnCapabilityQueueEnqueued,
  mockRecordTurnCapabilitySelectionSubmitted,
  mockRecordTurnCapabilitySendFailed,
  mockRedirectMessage,
  mockSendMessage,
  mockSetInputMessage,
  mockSteerMessage,
  mockToastInfo,
  mockValidateMessageQuota,
  resetMessageInputMocks,
} from './messageInputKit';

describe('useMessageInput submit telemetry integration', () => {
  beforeEach(resetMessageInputMocks);

  it('records query attempt and sends success-marked request on handleSubmit', async () => {
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
    expect(mockSendMessage).toHaveBeenCalledWith(
      'hello world',
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      true,
      undefined,
    );
  });

  it('records query attempt and enqueues message on handleQueueSubmit', async () => {
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleQueueSubmit();
    });

    expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
    expect(mockEnqueue).toHaveBeenCalledWith('hello world', [], undefined, null);
  });

  describe('an instruction the running turn cannot take', () => {
    it('queues a refused steer and tells the user it is sent after the current task', async () => {
      chatStoreRef.state = buildChatState({ loading: true });
      mockSteerMessage.mockResolvedValueOnce(false);
      mockEnqueue.mockReturnValue(2);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSteerSubmit();
      });

      expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
      expect(mockEnqueue).toHaveBeenCalledWith('hello world', [], undefined, null);
      expect(mockToastInfo).toHaveBeenCalledWith('queue.added_with_position:{"position":2}');
      expect(mockSendMessage).not.toHaveBeenCalled();
      expect(mockSetInputMessage).toHaveBeenCalledWith('');
    });

    it('queues a refused steer without a notice when the agent has gone idle', async () => {
      mockSteerMessage.mockResolvedValueOnce(false);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSteerSubmit();
      });

      expect(mockEnqueue).toHaveBeenCalledWith('hello world', [], undefined, null);
      expect(mockToastInfo).not.toHaveBeenCalled();
      expect(mockSendMessage).not.toHaveBeenCalled();
    });

    it('hands a failed redirect to steer as the same composed message and queues it, validating and recording once', async () => {
      const pendingSkill = { skillNames: ['pdf'] };
      chatStoreRef.state = buildChatState({
        loading: true,
        pendingExplicitSkillActivation: pendingSkill,
        setPendingExplicitSkillActivation: (value: unknown) => {
          chatStoreRef.state.pendingExplicitSkillActivation = value;
        },
      });
      mockRedirectMessage.mockResolvedValueOnce(false);
      mockSteerMessage.mockResolvedValueOnce(false);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleRedirectSubmit();
      });

      expect(mockRedirectMessage).toHaveBeenCalledWith('[use pdf] hello world');
      expect(mockSteerMessage).toHaveBeenCalledWith('[use pdf] hello world');
      expect(mockEnqueue).toHaveBeenCalledWith('[use pdf] hello world', [], undefined, null);
      expect(mockSendMessage).not.toHaveBeenCalled();
      expect(mockValidateMessageQuota).toHaveBeenCalledTimes(1);
      expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
    });

    it('does not queue a redirect the running turn accepted', async () => {
      chatStoreRef.state = buildChatState({ loading: true });
      mockRedirectMessage.mockResolvedValueOnce(true);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleRedirectSubmit();
      });

      expect(mockQueuePendingChatWikiQuerySuccess).toHaveBeenCalledTimes(1);
      expect(mockSteerMessage).not.toHaveBeenCalled();
      expect(mockEnqueue).not.toHaveBeenCalled();
      expect(mockSendMessage).not.toHaveBeenCalled();
    });
  });

  it('queues pending query success when steer succeeds', async () => {
    mockSteerMessage.mockResolvedValueOnce(true);
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleSteerSubmit();
    });

    expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
    expect(mockQueuePendingChatWikiQuerySuccess).toHaveBeenCalledTimes(1);
    expect(mockQueuePendingChatWikiQuerySuccess).toHaveBeenCalledWith([], 'chat-test', 'msg-live');
    expect(mockRecordChatWikiQuerySubmitted).not.toHaveBeenCalled();
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('applies one-turn capability override on handleSubmit', async () => {
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: null });
    });

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(mockSendMessage).toHaveBeenCalledWith(
      'hello world',
      undefined,
      undefined,
      undefined,
      undefined,
      expect.objectContaining({
        selectedSkillIds: ['skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
      }),
      true,
      {
        source: 'direct',
        effectiveSkillCount: 1,
        effectiveMcpCount: 2,
      },
    );
    expect(mockRecordTurnCapabilitySelectionSubmitted).toHaveBeenCalledTimes(1);
  });

  it('consumes one-turn capability selection on direct queue submit', async () => {
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: ['mcp-a'] });
    });

    await act(async () => {
      await result.current.handleQueueSubmit();
    });

    expect(mockEnqueue).toHaveBeenCalledWith('hello world', [], undefined, {
      skillIds: ['skill-b'],
      mcpNames: ['mcp-a'],
    });
    expect(mockRecordTurnCapabilitySelectionSubmitted).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilityQueueEnqueued).toHaveBeenCalledTimes(1);
  });

  it('records busy requeue without applied metric on direct busy fallback', async () => {
    const busyError = new Error('busy');
    busyError.name = 'AgentBusyError';
    mockSendMessage.mockRejectedValueOnce(busyError);
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: ['mcp-a'] });
    });

    await act(async () => {
      await result.current.handleSubmit();
      await Promise.resolve();
    });

    expect(mockRecordTurnCapabilitySelectionSubmitted).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilityBusyRequeued).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilityQueueEnqueued).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilityOverrideApplied).toHaveBeenCalledTimes(0);
  });

  it('maps direct send failure to enum reason', async () => {
    const networkError = new Error('network timeout');
    networkError.name = 'TypeError';
    mockSendMessage.mockRejectedValueOnce(networkError);
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: ['mcp-a'] });
    });

    await act(async () => {
      await result.current.handleSubmit();
      await Promise.resolve();
    });

    expect(mockRecordTurnCapabilitySendFailed).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilitySendFailed).toHaveBeenCalledWith('direct', 'network_error', 'chat:chat-test');
  });

  it('does not emit client failure metric for fatal 5xx failures', async () => {
    const { FatalNetworkError } = await import('@/lib/utils/networkResilience');
    mockSendMessage.mockRejectedValueOnce(new FatalNetworkError('upstream 500', { status: 500 }));
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: ['mcp-a'] });
    });

    await act(async () => {
      await result.current.handleSubmit();
      await Promise.resolve();
    });

    expect(mockRecordTurnCapabilitySendFailed).not.toHaveBeenCalled();
  });

  it('routes handleSubmit to redirectMessage when loading=true and busyInputMode is redirect (default)', async () => {
    chatStoreRef.state = buildChatState({
      loading: true,
      inputMessage: 'redirect instruction',
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(mockRedirectMessage).toHaveBeenCalledWith('redirect instruction');
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('routes handleSubmit to enqueue when loading=true and busyInputMode is queue', async () => {
    chatStoreRef.state = buildChatState({
      loading: true,
      inputMessage: 'follow-up task',
      agentConfig: {
        busyInputMode: 'queue',
      },
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(mockEnqueue).toHaveBeenCalledWith('follow-up task', [], undefined, null);
    expect(mockRedirectMessage).not.toHaveBeenCalled();
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('does not count a locally refused request as a settled capability override', async () => {
    mockSendMessage.mockResolvedValueOnce(false);
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: null });
    });
    await act(async () => {
      await result.current.handleSubmit();
      await Promise.resolve();
    });

    expect(mockRecordTurnCapabilityOverrideApplied).not.toHaveBeenCalled();
    expect(mockRecordTurnCapabilityOverrideNoop).not.toHaveBeenCalled();
  });
});
