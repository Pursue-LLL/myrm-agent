/**
 * [POS]
 * Chat SSE event handler slice (modelNotifyEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function modelNotifyEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type === H.AgentEventType.MODEL_ESCALATED) {
    const payload = data.data as {
      from_model?: string;
      to_model?: string;
      reason?: string;
    };
    if (payload) {
      const from = payload.from_model ?? 'unknown';
      const to = payload.to_model ?? 'unknown';
      const reason = payload.reason;
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const isZh = lang?.startsWith('zh');
      const baseMessage = isZh ? `模型已自动升级: ${from} → ${to}` : `Model auto-upgraded: ${from} → ${to}`;
      const toastMessage = reason
        ? isZh
          ? `${baseMessage}（原因: ${reason}）`
          : `${baseMessage} (reason: ${reason})`
        : baseMessage;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.info(toastMessage, { duration: 5000 });
      });

      actions.setMessages((state) => {
        const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          const steps = state.messages[messageIndex].progressSteps ?? [];
          steps.push({
            step_key: 'model_escalated',
            items: [{ text: toastMessage }],
            status: 'success',
          });
          state.messages[messageIndex].progressSteps = steps;
        }
      });
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.MODEL_FAILOVER) {
    const payload = data.data as
      | {
          fromModel?: string;
          toModel?: string;
          reason?: string;
          errorMessage?: string;
          cooldownMs?: number;
          attemptCount?: number;
        }
      | undefined;
    if (payload) {
      const from = payload.fromModel ?? 'unknown';
      const to = payload.toModel ?? 'unknown';
      const reason = payload.reason;
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const isZh = lang?.startsWith('zh');
      const baseMessage = isZh
        ? `模型已切换以避开故障: ${from} → ${to}`
        : `Model switched to dodge a fault: ${from} → ${to}`;
      const toastMessage = reason
        ? isZh
          ? `${baseMessage}（原因: ${reason}）`
          : `${baseMessage} (reason: ${reason})`
        : baseMessage;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.warning(toastMessage, { duration: 6000 });
      });

      actions.setMessages((state) => {
        const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          const steps = state.messages[messageIndex].progressSteps ?? [];
          steps.push({
            step_key: 'model_failover',
            items: [{ text: toastMessage }],
            status: 'success',
          });
          state.messages[messageIndex].progressSteps = steps;
        }
      });
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.MODEL_RECOVERY) {
    const payload = data.data as
      | {
          model?: string;
          downtimeMs?: number;
        }
      | undefined;
    if (payload?.model) {
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const isZh = lang?.startsWith('zh');
      const downtimeSec = payload.downtimeMs ? Math.round(payload.downtimeMs / 1000) : null;
      const toastMessage = isZh
        ? downtimeSec !== null
          ? `模型已恢复可用: ${payload.model}（停机 ${downtimeSec}s）`
          : `模型已恢复可用: ${payload.model}`
        : downtimeSec !== null
          ? `Model recovered: ${payload.model} (downtime ${downtimeSec}s)`
          : `Model recovered: ${payload.model}`;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.success(toastMessage, { duration: 4000 });
      });

      actions.setMessages((state) => {
        const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          const steps = state.messages[messageIndex].progressSteps ?? [];
          steps.push({
            step_key: 'model_recovery',
            items: [{ text: toastMessage }],
            status: 'success',
          });
          state.messages[messageIndex].progressSteps = steps;
        }
      });
    }
    return done(ctx);
  }


  return null;
}
