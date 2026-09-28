/**
 * [INPUT]
 * - types/agentStream/part1::AgentEventType (POS: Agent 流式事件类型枚举)
 * - messageUtils::findAssistantMessageIndex (POS: 查找助理消息索引工具函数)
 * - streamContext::StreamCtx (POS: 流上下文环境定义与控制函数)
 *
 * [OUTPUT]
 * - ttsrEvents: 捕获 ttsr_triggered 流式事件并原子记录安全规则拦截元数据到对应 assistant 消息状态
 *
 * [POS]
 * 消息流事件处理切片层。负责实时解析底座抛出的 TTSR 安全拦截事件并将其附加至聊天消息实体中。
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import { AgentEventType } from '../../types/agentStream/part1';
import { findAssistantMessageIndex } from '../../messageUtils';

export interface TtsrTriggeredPayload {
  rule_id: string;
  rule_name: string;
  reminder: string;
  target?: 'assistant' | 'thinking' | 'tool_args' | 'all';
  retry_count?: number;
  max_retries?: number;
  matched_text?: string;
}

export async function ttsrEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;

  if (data.type === AgentEventType.TTSR_TRIGGERED) {
    const payload = data.data as TtsrTriggeredPayload | undefined;
    if (payload) {
      actions.setMessages((state) => {
        let index = findAssistantMessageIndex(state.messages, data.messageId);
        if (index === -1) {
          index = state.messages.findLastIndex((m) => m.role === 'assistant');
        }
        if (index !== -1) {
          const targetMsg = state.messages[index];
          const existing = targetMsg.ttsrInterventions || [];
          targetMsg.ttsrInterventions = [
            ...existing,
            {
              ruleId: payload.rule_id,
              ruleName: payload.rule_name,
              reminder: payload.reminder,
              target: payload.target,
              retryCount: payload.retry_count ?? 1,
              maxRetries: payload.max_retries ?? 2,
              timestamp: new Date(),
            },
          ];
        }
      });
    }
    return done(ctx);
  }

  return null;
}
