/**
 * [POS]
 * Chat SSE event handler slice (sessionRecordingEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function sessionRecordingEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;

  if (data.type !== H.AgentEventType.SESSION_RECORDING) {
    return null;
  }

  const payload = data.data as
    | { filename?: string; preview_url?: string; content_type?: string }
    | undefined;

  if (!payload?.preview_url) {
    return done(ctx);
  }

  actions.setMessages((state) => {
    const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) {
      return;
    }
    state.messages[messageIndex].sessionRecording = {
      filename: payload.filename ?? 'session-recording.webm',
      preview_url: payload.preview_url,
      content_type: payload.content_type ?? 'video/webm',
    };
  });

  return done(ctx);
}
