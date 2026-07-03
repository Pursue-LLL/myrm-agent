/**
 * [POS]
 * Chat SSE event handler slice (agentControlEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function agentControlEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type === H.AgentEventType.ERROR) {
    let errorText: string;
    let hint: string | undefined;

    // Prioritize backend diagnostic_result (i18n + resolution steps)
    if (data.diagnostic_result) {
      const diagnostic = data.diagnostic_result;
      errorText = diagnostic.user_message;

      // Format resolution steps
      if (diagnostic.resolution_steps.length > 0) {
        const stepsText = diagnostic.resolution_steps.map((step, i) => `${i + 1}. ${step}`).join('\n');
        hint = stepsText;
      }
    } else {
      // Use frontend translation when backend sends an untranslated error token.
      const rawError = data.error || data.data || 'Unknown error';
      const friendlyError = await H.getUserFriendlyError(data.error_kind, rawError, data.cooldown_remaining_ms);
      errorText = friendlyError.message;
      hint = friendlyError.hint;
    }

    actions.setMessages((state) => {
      const errorStep = {
        step_key: 'processing_failed',
        items: [{ text: errorText }],
        error: hint || (true as boolean | string),
        recovery_actions: data.recovery_actions,
      };
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push(errorStep);
      } else {
        state.messages.push({
          content: '',
          messageId: data.messageId,
          chatId: state.messages[0]?.chatId || '',
          role: 'assistant',
          progressSteps: [errorStep],
          createdAt: new Date(),
          metadata: data.metadata,
        });
        ctx.added = true;
      }
    });

    if (data.retry_after_ms || data.cooldown_remaining_ms) {
      const retryAfterMs = data.retry_after_ms || data.cooldown_remaining_ms;
      const retryAfterSeconds = Math.ceil(retryAfterMs / 1000);
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const toastMessage = lang?.startsWith('zh')
        ? `已达到速率限制。请在 ${retryAfterSeconds} 秒后重试。`
        : `Rate limit exceeded. Please retry after ${retryAfterSeconds} seconds.`;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.error(toastMessage, { duration: Math.min(retryAfterMs, 10000) });
      });
    }

    actions.setLoading(false);
    void import('@/store/chat/goals/usePlanStore').then(({ usePlanStore }) => {
      usePlanStore.getState().clearActivePlan();
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.AGENT_CANCELLED) {
    const reason = data.data?.reason || 'user_cancelled';
    const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
    const isZh = lang?.startsWith('zh');
    const cancelText = reason === 'user_cancelled'
      ? (isZh ? '已取消' : 'Cancelled')
      : (isZh ? '已终止' : 'Terminated');

    actions.setMessages((state) => {
      const cancelStep = {
        step_key: 'agent_cancelled',
        items: [{ text: cancelText }],
        status: 'cancelled' as const,
      };
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push(cancelStep);
      }
    });
    actions.setLoading(false);
    // Release the processing lock on cancellation
    H.useToolApprovalStore.getState().unmarkProcessing(data.messageId);
    void import('@/store/chat/goals/usePlanStore').then(({ usePlanStore }) => {
      usePlanStore.getState().clearActivePlan();
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.STEERING) {
    const steerData = data.data as { count?: number; messages?: string[] } | string | undefined;
    let steerText = 'Steering applied';
    if (typeof steerData === 'object' && steerData?.messages?.length) {
      const preview = steerData.messages[0].slice(0, 80);
      const suffix = steerData.messages[0].length > 80 || steerData.messages.length > 1 ? '...' : '';
      steerText = `Steering: "${preview}${suffix}"`;
    }
    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push({
          step_key: 'steering_applied',
          items: [{ text: steerText }],
          status: 'success' as const,
        });
      }
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.ITERATION_LIMIT_REACHED) {
    const limitData = data.data as { limit?: number; nodes_completed?: number } | undefined;
    const limit = limitData?.limit ?? '?';
    const nodes = limitData?.nodes_completed ?? '?';

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push({
          step_key: 'iteration_limit_reached',
          items: [{ text: `${limit} iterations / ${nodes} nodes` }],
          status: 'warning' as const,
        });
      }
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.CONTEXT_OVERFLOW_RESET) {
    const { toast } = await import('@/lib/utils/toast');
    toast.warning(H.getContextOverflowMessage(), { duration: 8000 });
    H.useChatStore.getState().initializeChat(undefined);
    actions.setLoading(false);
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_FALLBACK) {
    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push({
          step_key: 'safety_fallback_active',
          tool_name: null,
          status: 'warning',
          items: [{ text: data.message }],
        });
      }
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.CONTEXT_REFERENCE_WARNING) {
    const { toast } = await import('@/lib/utils/toast');
    const warningMessage = data.data?.message || 'Context reference warning';
    toast.warning(warningMessage, { duration: 6000 });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.PTC_NOTIFY) {
    const payload = (data.data as Record<string, unknown> | undefined) ?? (data as unknown as Record<string, unknown>);
    const readField = <T>(name: string): T | undefined => {
      const fromPayload = payload ? (payload[name] as T | undefined) : undefined;
      if (fromPayload !== undefined && fromPayload !== null) {
        return fromPayload;
      }
      return (data as unknown as Record<string, T | undefined>)[name];
    };

    const message = readField<string>('message');
    const level = readField<'info' | 'warn' | 'alert'>('level') ?? 'info';
    const progress = readField<number>('progress');
    const stepIndex = readField<number>('step_index');
    const totalSteps = readField<number>('total_steps');
    const category = readField<string>('category');
    const errorCategory = readField<string>('error_category');

    if (!message) {
      return done(ctx);
    }

    // Inline activity: merge by category (or fallback bucket) into a single
    // progressSteps entry so 100x notify calls render as a single live card
    // with progress bar instead of stacking toasts.
    const stepKey = `ptc_notify:${category ?? 'default'}`;
    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        return;
      }
      const message_ = state.messages[messageIndex];
      if (!message_.progressSteps) {
        message_.progressSteps = [];
      }
      const existing = message_.progressSteps.find((s) => s.step_key === stepKey);
      const status: H.ProgressItem['status'] = level === 'alert' ? 'error' : level === 'warn' ? 'warning' : 'success';
      const reason = stepIndex !== undefined && totalSteps !== undefined ? `${stepIndex} / ${totalSteps}` : undefined;
      const patch: Partial<H.ProgressItem> = {
        step_key: stepKey,
        notify_message: message,
        notify_level: level,
        status,
      };
      if (progress !== undefined) {
        patch.notify_progress = progress;
        // Drive the existing ProgressSteps progress bar UI by mirroring into
        // the canonical ``progress_percent`` field; ensures pixel-perfect
        // reuse of theme colours and animations.
        patch.progress_percent = progress;
      }
      if (stepIndex !== undefined) {
        patch.notify_step_index = stepIndex;
      }
      if (totalSteps !== undefined) {
        patch.notify_total_steps = totalSteps;
      }
      if (category !== undefined) {
        patch.notify_category = category;
      }
      if (errorCategory !== undefined) {
        // Drive the destructive Badge in ProgressSteps; the harness emits
        // ``oom_killed`` / ``segfault`` / ``signal_terminated`` / ``nonzero_exit``
        // for background process exits so the user immediately sees *why* a
        // long-running task died.
        patch.error_category = errorCategory;
      }
      if (reason !== undefined) {
        patch.reason = reason;
      }
      if (existing) {
        Object.assign(existing, patch);
      } else {
        message_.progressSteps.push(patch as H.ProgressItem);
      }
    });

    // Loud levels also surface a transient toast so a critical signal is
    // not missed when the user is scrolled away from the activity card.
    if (level === 'alert' || level === 'warn') {
      const { toast } = await import('@/lib/utils/toast');
      if (level === 'alert') {
        toast.error(message, { duration: 8000 });
      } else {
        toast.warning(message, { duration: 6000 });
      }
    }
    return done(ctx);
  }

  return null;
}
