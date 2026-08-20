/**
 * [INPUT]
 * @/store/useChatStore::sendMessage, initializeChat (POS: Active chat state manager)
 * @/store/useWorkspaceStore::addPane (POS: Multi-pane workspace)
 *
 * [OUTPUT]
 * submitWorkflowTemplateRun: Arms a pinned template and sends the query in one step.
 *
 * [POS]
 * Shared helper for Settings workflow template library Run and future deep links.
 */

import { ensureActiveChatId } from '@/lib/chat/ensureActiveChatId';

export type SubmitWorkflowTemplateFailureReason = 'no_chat' | 'busy' | 'empty' | 'error';

export interface SubmitWorkflowTemplateRunOptions {
  templateId: string;
  displayName?: string;
  query: string;
  templateArgs?: Record<string, string> | null;
}

export async function submitWorkflowTemplateRun(
  options: SubmitWorkflowTemplateRunOptions,
): Promise<{ ok: true; chatId: string } | { ok: false; reason: SubmitWorkflowTemplateFailureReason }> {
  const templateId = options.templateId.trim();
  const query = options.query.trim();
  if (!templateId || !query) {
    return { ok: false, reason: 'empty' };
  }

  const chatId = await ensureActiveChatId();
  if (!chatId) {
    return { ok: false, reason: 'no_chat' };
  }

  const { default: useChatStore } = await import('@/store/useChatStore');
  const { loading, sendMessage } = useChatStore.getState();
  if (loading) {
    return { ok: false, reason: 'busy' };
  }

  useChatStore
    .getState()
    .setPendingWorkflowTemplate(templateId, options.templateArgs ?? null, options.displayName?.trim() || null);
  useChatStore.getState().setIsWorkflowMode(true);

  try {
    await sendMessage(query);
    return { ok: true, chatId };
  } catch {
    useChatStore.getState().clearPendingWorkflowTemplate();
    useChatStore.getState().setIsWorkflowMode(false);
    return { ok: false, reason: 'error' };
  }
}
