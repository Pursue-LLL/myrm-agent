/**
 * [INPUT]
 * - Browser CustomEvent API
 *
 * [OUTPUT]
 * - expandProgressStepsForMessage: open Task Steps panel for a chat message
 *
 * [POS]
 * Chat UI coordination (skill undo hint → expand progress steps).
 */

export const EXPAND_PROGRESS_STEPS_EVENT = 'myrm-expand-progress-steps';

export type ExpandProgressStepsDetail = {
  messageId: string;
};

export function expandProgressStepsForMessage(messageId: string): void {
  if (typeof window === 'undefined' || !messageId.trim()) {
    return;
  }
  window.dispatchEvent(
    new CustomEvent<ExpandProgressStepsDetail>(EXPAND_PROGRESS_STEPS_EVENT, {
      detail: { messageId: messageId.trim() },
    }),
  );
}
