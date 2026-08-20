/**
 * [POS]
 * Chat SSE event handler slice (routingMetaEvents).
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import type { TokenUsage } from '../../types/tokens';
import { done } from '../streamContext';
import * as H from './handlerDeps';

export async function routingMetaEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, added, actions } = ctx;
  if (data.type === H.AgentEventType.ROUTING_DECISION) {
    const routingData = data.data as
      | {
          tier?: 'simple' | 'standard' | 'reasoning' | 'complex';
          model_tier?: 'weak' | 'medium';
        }
      | undefined;
    const tier = routingData?.tier;
    const modelTier = routingData?.model_tier;
    if (typeof window !== 'undefined') {
      const afterPush = () => {
        try {
          const st = H.useChatStore.getState();
          const msgs = st.messages ?? [];
          return {
            msgCount: msgs.length,
            last: msgs.slice(-2).map((m) => ({
              role: m.role,
              id: m.messageId,
              tier: m.routingTier ?? null,
              keys: Object.keys(m),
            })),
          };
        } catch {
          return { err: 'read-store-failed' };
        }
      };
      const diag = {
        tier,
        modelTier,
        added,
        mid: data.messageId,
        at: Date.now(),
        after0: afterPush(),
        after500: (() => {
          const snap = afterPush();
          setTimeout(() => {
            const late = afterPush();
            const arr = (window as unknown as { __MYRM_ROUTING_DIAG__?: unknown[] }).__MYRM_ROUTING_DIAG__ ?? [];
            arr.push({ stage: 'after500', ...late });
            (window as unknown as { __MYRM_ROUTING_DIAG__?: unknown[] }).__MYRM_ROUTING_DIAG__ = arr;
          }, 500);
          return snap;
        })(),
      };
      const diagArr = (window as unknown as { __MYRM_ROUTING_DIAG__?: unknown[] }).__MYRM_ROUTING_DIAG__ ?? [];
      diagArr.push(diag);
      (window as unknown as { __MYRM_ROUTING_DIAG__?: unknown[] }).__MYRM_ROUTING_DIAG__ = diagArr;
      console.warn('[MYRM_ROUTING_DIAG]', JSON.stringify(diag));
    }
    if (tier || modelTier) {
      ctx.meta = {
        ...(ctx.meta ?? {}),
        ...(tier ? { routingTier: tier } : {}),
        ...(modelTier ? { modelTier } : {}),
      };
      if (!added) {
        actions.setMessages((state) => {
          state.messages.push({
            content: '',
            messageId: data.messageId,
            chatId: H.resolveStreamChatId(ctx.state),
            role: 'assistant',
            routingTier: tier,
            modelTier,
            createdAt: new Date(),
            metadata: data.metadata,
          });
        });
        ctx.added = true;
      } else {
        actions.setMessages((state) => {
          const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (messageIndex !== -1) {
            if (tier) {
              state.messages[messageIndex].routingTier = tier;
            }
            if (modelTier) {
              state.messages[messageIndex].modelTier = modelTier;
            }
          }
        });
      }
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.PRIVACY_LEVEL) {
    const privacyData = data.data;
    if (privacyData?.current_turn_level) {
      actions.setMessages((state) => {
        const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          state.messages[messageIndex].privacyLevel = privacyData.current_turn_level;
          if (privacyData.action) {
            state.messages[messageIndex].privacyAction = privacyData.action;
          }
        }
      });
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.PRIVACY_ROUTE) {
    const routeData = data.data;
    if (routeData?.route) {
      actions.setMessages((state) => {
        const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          state.messages[messageIndex].privacyRoute = routeData.route;
        }
      });
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOKEN_USAGE) {
    const tokenData = data.data as {
      usage: TokenUsage;
      cost_usd?: number;
      model_name?: string;
    };

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        state.messages[messageIndex].usage = tokenData.usage;
        if (tokenData.cost_usd !== undefined) {
          state.messages[messageIndex].costUsd = tokenData.cost_usd;
        }
        if (tokenData.model_name) {
          state.messages[messageIndex].modelName = tokenData.model_name;
        }
      }
    });

    return done(ctx);
  }

  return null;
}
