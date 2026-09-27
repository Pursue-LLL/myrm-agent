/**
 * [POS]
 * Chat SSE event handler slice (ttsrEvents).
 * Handles ttsr_triggered events from the TTSR engine to record stream rule interventions.
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import { AgentEventType } from '../../types/agentStream/part1';
import { findAssistantMessageIndex } from '../../messageUtils';

export interface TtsrTriggeredPayload {
  rule_id: string;
  rule_name: string;
  reminder: string;
  target?: 'assistant' | 'thinking' | 'tool_args' | 'all';
  retry_count?: number;
  max_retries?: number;
  matched_text?: string;
}

export async function ttsrEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;

  if (data.type === AgentEventType.TTSR_TRIGGERED) {
    const payload = data.data as TtsrTriggeredPayload | undefined;
    if (payload) {
      actions.setMessages((state) => {
        let index = findAssistantMessageIndex(state.messages, data.messageId);
        if (index === -1) {
          index = state.messages.findLastIndex((m) => m.role === 'assistant');
        }
        if (index !== -1) {
          const targetMsg = state.messages[index];
          const existing = targetMsg.ttsrInterventions || [];
          targetMsg.ttsrInterventions = [
            ...existing,
            {
              ruleId: payload.rule_id,
              ruleName: payload.rule_name,
              reminder: payload.reminder,
              target: payload.target,
              retryCount: payload.retry_count ?? 1,
              maxRetries: payload.max_retries ?? 2,
              timestamp: new Date(),
            },
          ];
        }
      });
    }
    return done(ctx);
  }

  return null;
}
