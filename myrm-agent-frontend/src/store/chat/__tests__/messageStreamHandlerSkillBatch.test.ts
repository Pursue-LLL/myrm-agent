import { describe, expect, it } from 'vitest';

import { AdaptiveScheduler } from '../adaptiveScheduler';
import { handleMessageStream, type StreamHandlerActions, type StreamHandlerState } from '../messageStreamHandler';
import { AgentEventType, type Message } from '../types';

const BATCH_ID = 'a1b2c3d4-e5f6-4789-a012-3456789abcde';
const MESSAGE_ID = 'assistant-skill-batch';

function createState(steps: NonNullable<Message['progressSteps']>): StreamHandlerState {
  return {
    messages: [
      {
        messageId: MESSAGE_ID,
        chatId: 'chat-1',
        createdAt: new Date('2026-10-13T00:00:00Z'),
        content: '',
        role: 'assistant',
        progressSteps: steps,
      },
    ],
    messageAppeared: false,
    loading: true,
    scheduler: new AdaptiveScheduler(),
  };
}

function createActions(state: StreamHandlerState): StreamHandlerActions {
  return {
    setMessages: (updater) => updater(state),
    setMessageAppeared: () => undefined,
    setLoading: () => undefined,
    _processSuggestions: async () => undefined,
    scheduleAutoSave: () => undefined,
  };
}

async function announceBatch(state: StreamHandlerState, toolName = 'skill_manage_tool'): Promise<void> {
  await handleMessageStream(
    { type: AgentEventType.TOOL_END, messageId: MESSAGE_ID, tool_name: toolName, skill_mutation_batch_id: BATCH_ID },
    '',
    undefined,
    false,
    '',
    state,
    createActions(state),
  );
}

describe('messageStreamHandler skill_manage batch announcement', () => {
  it('links the committed batch to the skill_manage step of the live turn', async () => {
    const state = createState([
      { step_key: 'skill_manage_tool_tool', tool_name: 'skill_manage_tool', tool_call_id: 'call-1' },
    ]);

    await announceBatch(state);

    expect(state.messages[0].progressSteps?.[0].skill_mutation_batch_id).toBe(BATCH_ID);
  });

  it('leaves steps of other tools untouched', async () => {
    const state = createState([
      { step_key: 'bash_code_execute_tool_tool', tool_name: 'bash_code_execute_tool', tool_call_id: 'call-1' },
    ]);

    await announceBatch(state);

    expect(state.messages[0].progressSteps?.[0].skill_mutation_batch_id).toBeUndefined();
  });

  it('keeps the batch the step already owns', async () => {
    const state = createState([
      {
        step_key: 'skill_manage_tool_tool',
        tool_name: 'skill_manage_tool',
        tool_call_id: 'call-1',
        skill_mutation_batch_id: 'b1b2c3d4-e5f6-4789-b012-3456789abcde',
      },
    ]);

    await announceBatch(state);

    expect(state.messages[0].progressSteps?.[0].skill_mutation_batch_id).toBe('b1b2c3d4-e5f6-4789-b012-3456789abcde');
  });
});
