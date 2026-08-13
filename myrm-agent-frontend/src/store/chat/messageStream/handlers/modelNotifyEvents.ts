/**
 * [POS]
 * Chat SSE event handler slice (modelNotifyEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";
import {
  MODEL_ESCALATED_REASON_KEY,
  MODEL_ESCALATED_TOAST_KEY,
  MODEL_RECOVERY_DOWNTIME_KEY,
  MODEL_RECOVERY_TOAST_KEY,
  resolveModelFailoverProgressStepKey,
  resolveModelFailoverToastKey,
} from "./modelNotifyToastKey";

export async function modelNotifyEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type === H.AgentEventType.MODEL_ESCALATED) {
    const payload = data.data as {
      from_model?: string;
      to_model?: string;
      reason?: string;
      restart?: boolean;
    };
    if (payload) {
      const from = payload.from_model ?? 'unknown';
      const to = payload.to_model ?? 'unknown';
      const reason = payload.reason;

      const { showI18nToast } = await import('@/services/i18nToastService');
      showI18nToast(MODEL_ESCALATED_TOAST_KEY, { from, to }, {
        descriptionKey: reason ? MODEL_ESCALATED_REASON_KEY : undefined,
        descriptionValues: reason ? { reason } : undefined,
        type: 'info',
        duration: 5000,
      });

      // Escalation clears the turn and re-plays it with a stronger model, so
      // any text containing the escalation marker is a draft to drop.
      if (payload.restart === true) {
        ctx.recievedMessage = '';
        // Drop any buffered render task whose stale closure would write the
        // pre-escalation draft back into the message.
        ctx.state.scheduler?.cancel?.();
      }
      actions.setMessages((state) => {
        let messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex === -1) {
          messageIndex = H.ensureAssistantStreamMessage(
            state.messages,
            data.messageId,
            state.messages[0]?.chatId || '',
          );
          if (messageIndex !== -1) {
            ctx.added = true;
          }
        }
        if (messageIndex !== -1) {
          if (payload.restart === true) {
            H.clearAssistantDraft(state.messages[messageIndex]);
          }
          const steps = state.messages[messageIndex].progressSteps ?? [];
          steps.push({
            step_key: 'model_escalated',
            items: [{ text: `${from} → ${to}` }],
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
      const toastKey = resolveModelFailoverToastKey(payload.reason);

      const { showI18nToast } = await import('@/services/i18nToastService');
      showI18nToast(toastKey, undefined, {
        description: `${from} → ${to}`,
        type: 'warning',
        duration: 6000,
      });

      // The primary model may have streamed partial text (or reasoning)
      // before failing; the fallback restarts the answer from scratch.
      // Drop that draft so it is not spliced with the complete answer.
      ctx.recievedMessage = '';
      // Drop any buffered render task whose stale closure would write the
      // pre-failover draft back into the message.
      ctx.state.scheduler?.cancel?.();
      actions.setMessages((state) => {
        let messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex === -1) {
          messageIndex = H.ensureAssistantStreamMessage(
            state.messages,
            data.messageId,
            state.messages[0]?.chatId || '',
          );
          if (messageIndex !== -1) {
            ctx.added = true;
          }
        }
        if (messageIndex !== -1) {
          H.clearAssistantDraft(state.messages[messageIndex]);
          const steps = state.messages[messageIndex].progressSteps ?? [];
          const displayKey = resolveModelFailoverProgressStepKey(payload.reason);
          const existingStep = steps.find(
            (step) =>
              step.step_key?.startsWith('model_failover') ||
              step.step_key === 'safety_fallback_active',
          );
          const failoverStep = {
            step_key: displayKey,
            items: [{ text: `${from} → ${to}` }],
            status: 'success' as const,
          };
          if (existingStep) {
            Object.assign(existingStep, failoverStep);
          } else {
            steps.push(failoverStep);
          }
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
      const downtimeSec =
        payload.downtimeMs !== undefined && payload.downtimeMs !== null
          ? Math.round(payload.downtimeMs / 1000)
          : null;

      const { showI18nToast } = await import('@/services/i18nToastService');
      showI18nToast(MODEL_RECOVERY_TOAST_KEY, { model: payload.model }, {
        descriptionKey:
          downtimeSec !== null ? MODEL_RECOVERY_DOWNTIME_KEY : undefined,
        descriptionValues:
          downtimeSec !== null ? { seconds: downtimeSec } : undefined,
        type: 'success',
        duration: 4000,
      });

      actions.setMessages((state) => {
        let messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex === -1) {
          messageIndex = H.ensureAssistantStreamMessage(
            state.messages,
            data.messageId,
            state.messages[0]?.chatId || '',
          );
          if (messageIndex !== -1) {
            ctx.added = true;
          }
        }
        if (messageIndex !== -1) {
          const steps = state.messages[messageIndex].progressSteps ?? [];
          steps.push({
            step_key: 'model_recovery',
            items: [{ text: payload.model ?? 'unknown' }],
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
