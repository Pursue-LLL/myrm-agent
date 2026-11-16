/**
 * [INPUT]
 * - @/store/chat/types::ActionMode (POS: @/store/chat/types 稳定入口；实现位于 types/。)
 *
 * [OUTPUT]
 * - shouldPreserveE2eActionMode: whether a send keeps the composer's action mode as it is
 * - shouldRunPrepareAutomationSend: whether a send may switch the mode through prepareAutomationSend
 *
 * [POS]
 * Action-mode policy of an automated send: fast mode reaches the server as it is, agent-mode sends may be prepared.
 */
import type { ActionMode } from '@/store/chat/types';

/** Fast mode must reach the server as-is (WEB_FAST / search_depth). */
export function shouldPreserveE2eActionMode(actionMode: ActionMode, explicitPreserve = false): boolean {
  return explicitPreserve || actionMode === 'fast';
}

/** Agent-mode E2E may call prepareAutomationSend; fast must not. */
export function shouldRunPrepareAutomationSend(preserveActionMode: boolean): boolean {
  return !preserveActionMode;
}
