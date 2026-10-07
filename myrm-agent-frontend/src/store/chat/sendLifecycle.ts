/**
 * [INPUT]
 * - @/store/chat/types::{AgentConfig, ChatState, File, QueuedAttachments} (POS: Chat domain state and request contracts)
 *
 * [OUTPUT]
 * - resolveRequestState: per-request view of the chat state (agent override + queued attachments).
 * - retractUserBubble: state updater that removes the optimistic user bubble of a request the server refused.
 *
 * [POS]
 * Pure helpers of the send lifecycle. Kept apart from messageRequest.ts so the queue-drain semantics
 * (a queued message sends its own attachments, a busy rejection leaves no ghost bubble) stay unit-testable.
 */
import type { AgentConfig, ChatState, File, QueuedAttachments } from '@/store/chat/types';

interface RequestStateSlice {
  agentConfig: AgentConfig | null;
  files: File[];
  cameraFrames: string[];
}

/**
 * Build the state view one request is assembled from. A queued message carries its own attachments, so the
 * live composer attachments (staged for the next message) are neither sent with it nor cleared after it.
 */
export function resolveRequestState<S extends RequestStateSlice>(
  state: S,
  agentConfigOverride: AgentConfig | null | undefined,
  queuedAttachments: QueuedAttachments | undefined,
): S {
  if (agentConfigOverride === undefined && !queuedAttachments) {
    return state;
  }
  return {
    ...state,
    ...(agentConfigOverride !== undefined && { agentConfig: agentConfigOverride }),
    ...(queuedAttachments && { files: queuedAttachments.files, cameraFrames: [] }),
  };
}

/**
 * Remove the trailing user bubble of `messageId`. The role check keeps a same-id assistant message
 * (HITL resume reuses the request id) from being removed instead.
 */
export function retractUserBubble(messageId: string): (state: ChatState) => void {
  return (state) => {
    const last = state.messages[state.messages.length - 1];
    if (last?.role === 'user' && last.messageId === messageId) {
      state.messages.pop();
    }
  };
}
