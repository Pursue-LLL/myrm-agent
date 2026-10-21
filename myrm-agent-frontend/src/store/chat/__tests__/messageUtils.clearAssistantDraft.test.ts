/**
 * clearAssistantDraft — restart protocol helper that drops a half-streamed
 * assistant draft (content / reasoning / reasoning timer) before a recovery
 * re-runs the turn from scratch (model failover, transient retry, escalation…).
 */
import { describe, expect, it } from 'vitest';

import { clearAssistantDraft } from '../messageUtils';
import type { Message, ProgressItem } from '../types';

function makeDraftMessage(overrides: Partial<Message> = {}): Message {
  return {
    content: 'Partial draft ',
    messageId: 'msg-1',
    chatId: 'c1',
    role: 'assistant',
    reasoning: 'partial reasoning',
    reasoningStartedAt: 1000,
    reasoningDurationMs: 500,
    progressSteps: [],
    createdAt: new Date(),
    ...overrides,
  } as Message;
}

describe('clearAssistantDraft', () => {
  it('clears content, reasoning and the reasoning timer', () => {
    const message = makeDraftMessage();

    clearAssistantDraft(message);

    expect(message.content).toBe('');
    expect(message.reasoning).toBe('');
    expect(message.reasoningStartedAt).toBeUndefined();
    expect(message.reasoningDurationMs).toBeUndefined();
  });

  it('keeps non-draft fields intact', () => {
    const steps: ProgressItem[] = [{ step_key: 'model_failover', items: [{ text: 'a → b' }], status: 'success' }];
    const message = makeDraftMessage({ progressSteps: steps });

    clearAssistantDraft(message);

    expect(message.messageId).toBe('msg-1');
    expect(message.chatId).toBe('c1');
    expect(message.role).toBe('assistant');
    expect(message.progressSteps).toBe(steps);
  });

  it('is idempotent on an already-empty draft', () => {
    const message = makeDraftMessage({ content: '', reasoning: '' });

    clearAssistantDraft(message);
    clearAssistantDraft(message);

    expect(message.content).toBe('');
    expect(message.reasoning).toBe('');
  });
});
