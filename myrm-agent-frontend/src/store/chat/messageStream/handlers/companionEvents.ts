/**
 * [POS]
 * Chat SSE event handler slice (companionEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function companionEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type === 'mascot_xp_update') {
    try {
      const companionStore = (await import('@/store/useCompanionStore')).default;
      companionStore.getState().setMascotXpState(data.data);
    } catch {
      // safe fallback
    }
    return done(ctx);
  }

  // Handle DAG state updates
  if (data.type === 'dag_state_update') {
    try {
      const companionStore = (await import('@/store/useCompanionStore')).default;
      companionStore.getState().setDagData(data.data as Record<string, unknown> | null);
    } catch {
      // safe fallback
    }
    return done(ctx);
  }

  if (data.type === 'catchup_snapshot') {
    const snap = data.data;
    actions.setMessages((state) => {
      const msgIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (msgIndex !== -1) {
        const msg = state.messages[msgIndex];
        msg.content = snap.content || '';
        msg.thinkingItems = snap.reasoning ? [snap.reasoning] : [];
        msg.progressSteps = snap.progress_steps || [];
        msg.sources = snap.sources || [];
      }
    });
    return done(ctx);
  }

  return null;
}
