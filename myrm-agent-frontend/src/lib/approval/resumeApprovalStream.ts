import { toast } from 'sonner';

import type { ToolApprovalRequest } from '@/store/chat/types';
import type { ResumeDecisionsPayload } from '@/lib/approval/approvalDecision';
import { AdaptiveScheduler } from '@/store/chat/adaptiveScheduler';
import type { StreamHandlerState, StreamMutableState } from '@/store/chat/messageStreamHandler';
import {
  getModelSelection,
  getLiteModelSelection,
  getFallbackModelSelection,
  getFallbackLiteModelSelection,
} from '@/store/chat/messageRequest';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';

/**
 * [INPUT] ToolApprovalRequest anchor + resume decisions payload
 * [OUTPUT] SSE stream resume via createAISearchStream
 * [POS] Single source for approval resume used by hook bulk/single paths
 */

export type { ApprovalDecision, ResumeDecisionsPayload, ToolApprovalResolveExtra } from '@/lib/approval/approvalDecision';
export { buildApprovalDecision } from '@/lib/approval/approvalDecision';

export async function resumeApprovalStream(
  request: ToolApprovalRequest,
  resumeValue: ResumeDecisionsPayload,
  resumeErrorMessage: string,
): Promise<void> {
  const { default: useChatStore } = await import('@/store/useChatStore');
  const chatState = useChatStore.getState();

  const modelSelection = getModelSelection(request.actionMode, chatState.agentConfig);
  const liteModelSelection = getLiteModelSelection();
  const fallbackModelSelection = getFallbackModelSelection(request.actionMode, chatState.agentConfig);
  const fallbackLiteModelSelection = getFallbackLiteModelSelection();

  if (!modelSelection) {
    toast.error(resumeErrorMessage);
    throw new Error('Missing model selection for approval resume');
  }

  const { createAISearchStream } = await import('@/services/chat');
  const requestBody = {
    query: '',
    message_id: request.messageId,
    chat_id: request.chatId,
    action_mode: request.actionMode,
    resume_value: resumeValue,
    model_selection: modelSelection,
    timezone: getBrowserTimezone(),
    ...(liteModelSelection && { lite_model_selection: liteModelSelection }),
    ...(fallbackModelSelection && { fallback_model_selection: fallbackModelSelection }),
    ...(fallbackLiteModelSelection && {
      fallback_lite_model_selection: fallbackLiteModelSelection,
    }),
    ...(chatState.agentConfig && {
      agent_config: {
        skill_ids: chatState.agentConfig.selectedSkillIds,
        enabled_builtin_tools: chatState.agentConfig.enabledBuiltinTools ?? [],
      },
    }),
  };

  const response = await createAISearchStream(requestBody, chatState.abortController || undefined);
  const { handleMessageStream } = await import('@/store/chat/messageStreamHandler');
  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) {
    console.error('[APPROVAL] No response body');
    throw new Error('Approval resume stream has no body');
  }

  let added = false;
  let recievedMessage = '';
  const sources: import('@/store/chat/types').Source[] = [];
  const scheduler = new AdaptiveScheduler();
  const streamState: StreamHandlerState = {
    messages: chatState.messages,
    messageAppeared: chatState.messageAppeared,
    loading: chatState.loading,
    scheduler,
  };

  const setMessagesAdapter = (updater: (state: StreamMutableState) => void) => {
    useChatStore.setState((draft) => {
      updater(draft);
    });
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n').filter((line) => line.trim().startsWith('data:'));

    for (const line of lines) {
      try {
        const json = JSON.parse(line.replace(/^data:\s*/, ''));
        const result = await handleMessageStream(json, '', sources, added, recievedMessage, streamState, {
          setMessages: setMessagesAdapter,
          setMessageAppeared: chatState.setMessageAppeared || (() => {}),
          setLoading: chatState.setLoading || (() => {}),
          _processSuggestions: chatState._processSuggestions || (async () => {}),
          scheduleAutoSave: chatState.scheduleAutoSave || (() => {}),
        });
        added = result.added;
        recievedMessage = result.recievedMessage;
      } catch (error) {
        console.error('[APPROVAL] Stream parse error:', error);
      }
    }
  }

  scheduler.flush();
  scheduler.cancel();
}
