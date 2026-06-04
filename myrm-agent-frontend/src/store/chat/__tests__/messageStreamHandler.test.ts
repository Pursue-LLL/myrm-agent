import { describe, expect, it, vi } from 'vitest';
import { AdaptiveScheduler } from '../adaptiveScheduler';
import { handleMessageStream, type StreamHandlerActions, type StreamHandlerState } from '../messageStreamHandler';
import { AgentEventType, type Message } from '../types';

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

const createAssistantState = (messageId: string): StreamHandlerState => {
  const assistant: Message = {
    messageId,
    chatId: 'chat-1',
    createdAt: new Date('2026-06-04T00:00:00Z'),
    content: '',
    role: 'assistant',
    progressSteps: [],
  };
  return {
    messages: [assistant],
    messageAppeared: false,
    loading: true,
    scheduler: new AdaptiveScheduler(),
  };
};

const createStatefulActions = (state: StreamHandlerState): StreamHandlerActions => ({
  setMessages: (updater) => updater(state),
  setMessageAppeared: () => undefined,
  setLoading: (loading) => {
    state.loading = typeof loading === 'function' ? loading(state.loading) : loading;
  },
  _processSuggestions: async () => undefined,
  scheduleAutoSave: () => undefined,
});

const findProgressStepText = (
  state: StreamHandlerState,
  messageId: string,
  stepKey: string,
): string | undefined => {
  const message = state.messages.find((m) => m.messageId === messageId);
  const step = message?.progressSteps?.find((s) => s.step_key === stepKey);
  const item = step?.items?.[0];
  return item && typeof item === 'object' && 'text' in item ? String(item.text) : undefined;
};

describe('messageStreamHandler - diagnostic_result priority logic', () => {
  it('should prioritize diagnostic_result over frontend translation', async () => {
    const messageId = 'assistant-error-1';
    const state = createAssistantState(messageId);

    await handleMessageStream(
      {
        type: AgentEventType.ERROR,
        messageId,
        error: 'API key is invalid',
        error_kind: 'LLM_ERROR',
        diagnostic_result: {
          error_type: 'api_key',
          user_message: 'Invalid API key from backend i18n',
          resolution_steps: [
            'Check your API key in settings',
            'Verify API key format',
            'Visit https://platform.openai.com/api-keys for help',
          ],
          locale: 'en',
        },
      },
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    const errorText = findProgressStepText(state, messageId, 'processing_failed');
    expect(errorText).toBe('Invalid API key from backend i18n');

    const step = state.messages[0].progressSteps?.find((s) => s.step_key === 'processing_failed');
    expect(step?.error).toContain('1. Check your API key in settings');
    expect(step?.error).toContain('2. Verify API key format');
    expect(step?.error).toContain('3. Visit https://platform.openai.com/api-keys for help');
  });

  it('should use fallback path when diagnostic_result is missing', async () => {
    const messageId = 'assistant-error-2';
    const state = createAssistantState(messageId);

    await handleMessageStream(
      {
        type: AgentEventType.ERROR,
        messageId,
        error: 'API key is invalid',
        error_kind: 'LLM_ERROR',
      },
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    expect(findProgressStepText(state, messageId, 'processing_failed')).toBe('API key is invalid');
    const step = state.messages[0].progressSteps?.find((s) => s.step_key === 'processing_failed');
    expect(step?.error).toBe(true);
    expect(state.loading).toBe(false);
  });

  it('should handle diagnostic_result with empty resolution_steps', async () => {
    const messageId = 'assistant-error-3';
    const state = createAssistantState(messageId);

    await handleMessageStream(
      {
        type: AgentEventType.ERROR,
        messageId,
        error: 'Unknown error',
        error_kind: 'LLM_ERROR',
        diagnostic_result: {
          error_type: 'unknown',
          user_message: 'Unknown error occurred',
          resolution_steps: [],
          locale: 'en',
        },
      },
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    expect(findProgressStepText(state, messageId, 'processing_failed')).toBe('Unknown error occurred');
    const step = state.messages[0].progressSteps?.find((s) => s.step_key === 'processing_failed');
    expect(step?.error).toBe(true);
  });
});

describe('messageStreamHandler - STEERING event parsing', () => {
  const messageId = 'assistant-steer-1';

  const runSteering = async (
    data: { count?: number; messages?: string[] } | string | undefined,
  ): Promise<StreamHandlerState> => {
    const state = createAssistantState(messageId);
    await handleMessageStream(
      {
        type: AgentEventType.STEERING,
        messageId,
        data,
      },
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );
    return state;
  };

  it('should show preview of short single message', async () => {
    const state = await runSteering({ count: 1, messages: ['focus on testing'] });
    expect(findProgressStepText(state, messageId, 'steering_applied')).toBe('Steering: "focus on testing"');
  });

  it('should truncate message longer than 80 chars', async () => {
    const longMsg = 'A'.repeat(120);
    const state = await runSteering({ count: 1, messages: [longMsg] });
    expect(findProgressStepText(state, messageId, 'steering_applied')).toBe(`Steering: "${'A'.repeat(80)}..."`);
  });

  it('should add ellipsis for multiple messages', async () => {
    const state = await runSteering({ count: 2, messages: ['first', 'second'] });
    expect(findProgressStepText(state, messageId, 'steering_applied')).toBe('Steering: "first..."');
  });

  it('should fallback for undefined data', async () => {
    const state = await runSteering(undefined);
    expect(findProgressStepText(state, messageId, 'steering_applied')).toBe('Steering applied');
  });

  it('should fallback for string data (backward compat)', async () => {
    const state = await runSteering('Steering with 2 new message(s)' as unknown as undefined);
    expect(findProgressStepText(state, messageId, 'steering_applied')).toBe('Steering applied');
  });

  it('should fallback for empty messages array', async () => {
    const state = await runSteering({ count: 0, messages: [] });
    expect(findProgressStepText(state, messageId, 'steering_applied')).toBe('Steering applied');
  });

  it('should handle Chinese/Unicode in preview', async () => {
    const state = await runSteering({ count: 1, messages: ['请专注于中文搜索结果'] });
    expect(findProgressStepText(state, messageId, 'steering_applied')).toBe('Steering: "请专注于中文搜索结果"');
  });

  it('should handle message with newlines (no truncation under 80)', async () => {
    const msg = 'line1\nline2\nline3';
    const state = await runSteering({ count: 1, messages: [msg] });
    expect(findProgressStepText(state, messageId, 'steering_applied')).toBe(`Steering: "${msg}"`);
  });
});
