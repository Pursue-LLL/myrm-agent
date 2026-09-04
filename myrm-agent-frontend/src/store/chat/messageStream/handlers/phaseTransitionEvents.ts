/**
 * [POS]
 * Chat SSE event handler slice (phaseTransitionEvents).
 *
 * Updates assistant message with active macro phase (1-3) and active execution lane (6 lanes)
 * for the ThreePhaseMultiLaneExecutionStepper component.
 */

import type { PhaseTransitionPayload } from '@/store/chat/types/agentStream/part1';
import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import * as H from './handlerDeps';

export async function phaseTransitionEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type === H.AgentEventType.PHASE_TRANSITION) {
    const rawData = data.data;
    if (!rawData || typeof rawData !== 'object') {
      return done();
    }

    const payload = rawData as PhaseTransitionPayload;
    const messageId = data.messageId;

    actions.setMessages((state) => {
      const idx = H.findAssistantMessageIndex(state.messages, messageId);
      if (idx !== -1) {
        state.messages[idx].phaseExecution = payload;
        state.messages[idx].executionLane = payload.active_lane;
        const history = state.messages[idx].phaseHistory ?? [];
        // Prevent adjacent duplicates
        const last = history[history.length - 1];
        if (
          !last ||
          last.phase !== payload.phase ||
          last.active_lane !== payload.active_lane ||
          last.node_id !== payload.node_id
        ) {
          state.messages[idx].phaseHistory = [...history, payload];
        }
      }
    });

    return done();
  }

  return null;
}
