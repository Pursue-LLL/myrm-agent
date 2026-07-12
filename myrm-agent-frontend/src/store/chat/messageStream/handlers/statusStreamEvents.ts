/**
 * [POS]
 * Chat SSE event handler slice (statusStreamEvents).
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import * as H from './handlerDeps';
import { applyStatusPhaseData } from './statusStreamPhaseData';
import { applyStatusProgressStep, isStatusProgressStep } from './statusStreamProgressSteps';

export async function statusStreamEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type === H.AgentEventType.STATUS) {
    const stepKey = data.step_key;

    if (typeof window !== 'undefined' && stepKey) {
      window.dispatchEvent(new CustomEvent('pet-status-event', { detail: { step_key: stepKey } }));
    }

    if (stepKey && isStatusProgressStep(stepKey)) {
      await applyStatusProgressStep(ctx, stepKey);
    }

    if (stepKey === 'cache_break') {
      const sd = data.data as Record<string, unknown> | undefined;
      const reason = typeof sd?.reason === 'string' ? sd.reason : '';
      const suggestedActions = typeof sd?.suggested_actions === 'string' ? sd.suggested_actions : '';
      if (reason) {
        actions.setMessages((state) => {
          const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1) {
            state.messages[idx].cacheBreakReason = reason;
            if (suggestedActions) {
              state.messages[idx].cacheSuggestedActions = suggestedActions;
            }
          }
        });
        const notifyEnabled = H.useConfigStore.getState().enableCacheBreakNotification;
        if (notifyEnabled) {
          const tokenDrop = typeof sd?.token_drop === 'number' ? sd.token_drop : 0;
          const dropText = tokenDrop > 1000 ? `, ~${Math.round(tokenDrop / 1000)}k tokens uncached` : '';
          import('@/lib/utils/toast').then(({ toast }) => {
            toast.info(`Cache reset: ${reason}${dropText}`, { duration: 5000 });
          });
        }
      }
    }

    if (stepKey === 'analyzing_image_clear' || stepKey === 'analyzing_video_clear') {
      const analysisStepKey = stepKey === 'analyzing_image_clear' ? 'analyzing_image' : 'analyzing_video';
      window.setTimeout(() => {
        actions.setMessages((state) => {
          const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (messageIndex !== -1 && state.messages[messageIndex].progressSteps) {
            state.messages[messageIndex].progressSteps = state.messages[messageIndex].progressSteps!.filter(
              (step) => step.step_key !== analysisStepKey,
            );
            state.messages[messageIndex].mediaAnalysisStatus = null;
          }
        });
      }, 250);
    }

    const statusData = data.data;
    if (typeof statusData === 'object' && statusData !== null) {
      applyStatusPhaseData(ctx, statusData as Record<string, unknown>);
    }

    return done(ctx);
  }

  return null;
}
