/**
 * [INPUT]
 * - @/store/chat/types::{AgentConfig, ChatState, File, QueuedAttachments} (POS: Chat domain state and request contracts)
 *
 * [OUTPUT]
 * - resolveRequestState: per-request view of the chat state (agent override + queued attachments).
 * - retractUserBubble: state updater that removes the optimistic user bubble of a request the server refused.
 * - sendFailureToast: toast options reporting a failed turn without exposing raw error texts.
 * - isHeldByOtherTurn: whether a newer turn holds the shared abort handle, so an ended turn must not release the shared turn state.
 *
 * [POS]
 * Pure helpers of the send lifecycle. Kept apart from messageRequest.ts so the queue-drain semantics
 * (a queued message sends its own attachments, a busy rejection leaves no ghost bubble), the turn ownership rule
 * (an ended turn never resets the state of the turn that replaced it) and the wording policy for failed turns
 * stay unit-testable.
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
 * Whether a newer turn holds the shared abort handle. Only the owner of the handle may release the turn state it
 * guards: a turn can end after the next one took over (it still reconciles with the server, or a stop reached it
 * while it waited for the workspace stream), and resetting then would leave the running turn without a Stop button.
 * A pane snapshot is a JSON clone, so a handle read from it is a plain object rather than a live controller and
 * counts as held by nobody.
 */
export function isHeldByOtherTurn(held: unknown, own: AbortController): boolean {
  return held instanceof AbortController && held !== own;
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

/**
 * Toast options reporting a failed turn: the connection hint after a network failure, the server's own
 * explanation when a refusal carried one, a fixed line otherwise. Raw error texts (internal exceptions, proxy
 * error pages) never reach the UI; they belong in the console.
 */
export function sendFailureToast(isNetworkError: boolean, refusalDetail: string | undefined) {
  if (isNetworkError) {
    return { descriptionKey: 'chat.messageFailed.networkError', type: 'error', duration: 8000 } as const;
  }
  if (refusalDetail) {
    return {
      descriptionKey: 'chat.messageFailed.description',
      descriptionValues: { error: refusalDetail },
      type: 'error',
      duration: 3000,
    } as const;
  }
  return { descriptionKey: 'chat.messageFailed.generic', type: 'error', duration: 3000 } as const;
}
