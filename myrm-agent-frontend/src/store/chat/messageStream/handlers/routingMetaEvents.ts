/**
 * [POS]
 * Chat SSE event handler slice (routingMetaEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function routingMetaEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, added, actions } = ctx;
  if (data.type === H.AgentEventType.ROUTING_DECISION) {
    const routingData = data.data;
    const tier = routingData?.tier as 'simple' | 'standard' | 'reasoning' | 'complex' | undefined;
    if (tier) {
      if (!added) {
        actions.setMessages((state) => {
          state.messages.push({
            content: '',
            messageId: data.messageId,
            chatId: state.messages[0]?.chatId || '',
            role: 'assistant',
            routingTier: tier,
            createdAt: new Date(),
            metadata: data.metadata,
          });
        });
        ctx.added = true;
      } else {
        actions.setMessages((state) => {
          const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (messageIndex !== -1) {
            state.messages[messageIndex].routingTier = tier;
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
      usage: import('./types').TokenUsage;
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
