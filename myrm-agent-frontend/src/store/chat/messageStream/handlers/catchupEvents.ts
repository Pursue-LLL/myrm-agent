/**
 * [INPUT]
 * ../streamContext::StreamCtx (POS: per-SSE-event reducer context)
 * ./handlerDeps::findAssistantMessageIndex, mergeMessageSources (POS: message lookup and source merge helpers)
 *
 * [OUTPUT]
 * catchupEvents: CATCHUP_SNAPSHOT SSE handler that replaces the assistant message with the server snapshot.
 *
 * [POS]
 * SSE handler for the snapshot a re-attached stream sends first.
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import * as H from './handlerDeps';

export async function catchupEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type !== 'catchup_snapshot') {
    return null;
  }

  const snap = data.data;
  actions.setMessages((state) => {
    let msgIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (msgIndex === -1) {
      msgIndex = state.messages.findLastIndex((m) => m.role === 'assistant');
    }
    if (msgIndex !== -1) {
      const msg = state.messages[msgIndex];
      msg.content = snap.content || '';
      msg.thinkingItems = snap.reasoning ? [snap.reasoning] : [];
      msg.progressSteps = snap.progress_steps || [];
      // Never wipe in-stream sources with an empty catchup payload.
      if (Array.isArray(snap.sources) && snap.sources.length > 0) {
        msg.sources = H.mergeMessageSources(msg.sources || [], snap.sources);
      }
    }
  });
  return done(ctx);
}
