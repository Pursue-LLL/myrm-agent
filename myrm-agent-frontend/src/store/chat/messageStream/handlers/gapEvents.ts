/**
 * [POS]
 * SSE handlers for capability/skill entitlement gaps from stream preflight and discover_capability_tool.
 */

import type { Message } from '@/store/chat/types';
import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import * as H from './handlerDeps';
import {
  BUILTIN_TOOL_LABELS,
  isBuiltinToolId,
  type BuiltinToolId,
} from '@/store/chat/types/builtinTools';
import { toast } from '@/lib/utils/toast';

function resolveLastPlainUserMessage(messages: Message[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== 'user') {
      continue;
    }
    const content = message.content;
    if (typeof content === 'string' && content.trim()) {
      return content.trim();
    }
  }
  return null;
}

function createRetryMessageId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `gap-retry-${Date.now()}`;
}

async function retryLastUserMessageIfIdle(): Promise<boolean> {
  const store = H.useChatStore.getState();
  if (store.loading) {
    return false;
  }
  const retryText = resolveLastPlainUserMessage(store.messages);
  if (!retryText) {
    return false;
  }
  await store.sendMessage(retryText, createRetryMessageId());
  return true;
}

export async function gapEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data } = ctx;
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
  const isZh = lang?.startsWith('zh');

  if (data.type === H.AgentEventType.CAPABILITY_GAP) {
    const payload = data.data as { tool_id?: string; tool_group?: string } | undefined;
    const toolId = payload?.tool_id;
    if (!toolId || !isBuiltinToolId(toolId)) {
      return null;
    }

    const label = isZh ? BUILTIN_TOOL_LABELS[toolId].zh : BUILTIN_TOOL_LABELS[toolId].en;
    const message = isZh
      ? `完成此任务需要开启「${label}」`
      : `Enable "${label}" to complete this task`;
    const actionLabel = isZh ? '开启并重发' : 'Enable & resend';

    toast.info(message, {
      duration: 12000,
      action: {
        label: actionLabel,
        onClick: async () => {
          const store = H.useChatStore.getState();
          const prev = store.currentBuiltinTools;
          if (!prev.includes(toolId)) {
            store.setCurrentBuiltinTools([...prev, toolId as BuiltinToolId]);
          }
          const resent = await retryLastUserMessageIfIdle();
          if (resent) {
            toast.success(
              isZh ? '已开启并重新发送您的请求' : 'Enabled and resent your request.',
            );
            return;
          }
          toast.success(
            isZh ? '已开启，请重试刚才的请求' : 'Enabled. Please retry your request.',
          );
        },
      },
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.SKILL_GAP) {
    const payload = data.data as { skill_id?: string } | undefined;
    const skillId = payload?.skill_id;
    if (!skillId) {
      return null;
    }

    const message = isZh
      ? `完成此任务需要绑定技能「${skillId}」`
      : `Bind skill "${skillId}" to complete this task`;
    const actionLabel = isZh ? '绑定并重发' : 'Bind & resend';

    toast.info(message, {
      duration: 12000,
      action: {
        label: actionLabel,
        onClick: async () => {
          const store = H.useChatStore.getState();
          const prev = store.agentConfig?.selectedSkillIds ?? [];
          if (!prev.includes(skillId)) {
            store.updateAgentConfig({ selectedSkillIds: [...prev, skillId] });
          }
          const resent = await retryLastUserMessageIfIdle();
          if (resent) {
            toast.success(
              isZh ? '已绑定并重新发送您的请求' : 'Skill bound and resent your request.',
            );
            return;
          }
          toast.success(isZh ? '已绑定，请重试刚才的请求' : 'Skill bound. Please retry your request.');
        },
      },
    });
    return done(ctx);
  }

  return null;
}
