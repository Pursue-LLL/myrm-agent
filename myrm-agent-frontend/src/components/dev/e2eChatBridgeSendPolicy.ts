import type { ActionMode } from '@/store/chat/types';

/** Fast mode must reach the server as-is (WEB_FAST / search_depth). */
export function shouldPreserveE2eActionMode(actionMode: ActionMode, explicitPreserve = false): boolean {
  return explicitPreserve || actionMode === 'fast';
}

/** Agent-mode E2E may call prepareAutomationSend; fast must not. */
export function shouldRunPrepareAutomationSend(preserveActionMode: boolean): boolean {
  return !preserveActionMode;
}
