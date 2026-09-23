/**
 * [POS] 工作记忆工作台 SSE 处理器切片。负责将 Agent 工作记忆变更事件分发为前端响应式事件。
 * [INPUT] ../streamContext::StreamCtx (POS: SSE 流处理上下文)
 * [INPUT] @/store/chat/types::AgentEventType (POS: Agent 事件枚举定义)
 * [OUTPUT] workingMemoryEvents: 处理 working_memory SSE 事件并派发 window CustomEvent
 * [OUTPUT] WorkingMemoryEventPayload: 工作记忆事件载荷接口
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import { AgentEventType } from '@/store/chat/types';

export interface WorkingMemoryEventPayload {
  data?: Record<string, unknown>;
  action?: string;
}

function resolveChatId(state: StreamCtx['state']): string {
  return state.chatId?.trim() || state.messages?.[0]?.chatId?.trim() || '';
}

export async function workingMemoryEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data } = ctx;
  if (data.type !== AgentEventType.WORKING_MEMORY) {
    return null;
  }

  if (typeof window !== 'undefined' && data.data && typeof data.data === 'object') {
    const action = typeof (data as WorkingMemoryEventPayload).action === 'string'
      ? (data as WorkingMemoryEventPayload).action
      : undefined;

    window.dispatchEvent(
      new CustomEvent('working_memory_update', {
        detail: {
          data: data.data,
          sessionId: resolveChatId(ctx.state),
          action,
        },
      })
    );
  }

  return done(ctx);
}
