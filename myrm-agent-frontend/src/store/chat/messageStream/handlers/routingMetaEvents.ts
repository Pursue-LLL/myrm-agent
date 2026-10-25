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
          tier?: 'simple' | 'standard' | 'reasoning' | 'complex' | 'code' | 'long_doc';
          specialty?: 'code' | 'long_doc' | 'reasoning' | 'multimodal' | 'casual' | 'general';
          reason?: string;
          model_tier?: 'weak' | 'medium';
        }
      | undefined;
    const tier = routingData?.tier;
    const specialty = routingData?.specialty;
    const reason = routingData?.reason;
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
    if (tier || specialty || reason || modelTier) {
      ctx.meta = {
        ...(ctx.meta ?? {}),
        ...(tier ? { routingTier: tier } : {}),
        ...(specialty ? { routingSpecialty: specialty } : {}),
        ...(reason ? { routingReason: reason } : {}),
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
            routingSpecialty: specialty,
            routingReason: reason,
            modelTier,
            createdAt: new Date(),
            metadata: data.metadata,
          });
          // 路由帧代表本轮已在服务端启动：在同一份 draft 里立刻标记 messageAppeared，
          // 让 UI 从静态骨架切到带呼吸动画+秒表的气泡（在 updater 外改 state 不会通知订阅者）。
          if (!state.messageAppeared) {
            state.messageAppeared = true;
          }
        });
        ctx.added = true;
      } else {
        actions.setMessages((state) => {
          const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (messageIndex !== -1) {
            if (tier) {
              state.messages[messageIndex].routingTier = tier;
            }
            if (specialty) {
              state.messages[messageIndex].routingSpecialty = specialty;
            }
            if (reason) {
              state.messages[messageIndex].routingReason = reason;
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
    const rawData = (data.data || {}) as Record<string, unknown>;

    let resolvedUsage: TokenUsage;
    let resolvedCostUsd: number | undefined;
    let resolvedModelName: string | undefined;

    if (rawData.usage && typeof rawData.usage === 'object') {
      // Shape A: Standard nested usage payload
      const nestedUsage = rawData.usage as TokenUsage;
      resolvedUsage = {
        ...nestedUsage,
        auth_mode: (rawData.auth_mode as string) || nestedUsage.auth_mode,
        billable: rawData.billable !== undefined ? Boolean(rawData.billable) : nestedUsage.billable,
        source: (rawData.source as string) || nestedUsage.source,
      };
      resolvedCostUsd = typeof rawData.cost_usd === 'number' ? (rawData.cost_usd as number) : undefined;
      resolvedModelName = typeof rawData.model_name === 'string' ? (rawData.model_name as string) : undefined;
    } else {
      // Shape B: External delegation flat payload (acp / external_agents)
      const inputTokens = Number(rawData.input_tokens ?? rawData.prompt_tokens ?? 0);
      const outputTokens = Number(rawData.output_tokens ?? rawData.completion_tokens ?? 0);
      const totalTokens = Number(rawData.total_tokens ?? inputTokens + outputTokens);
      const authMode = (rawData.auth_mode as string) || 'subscription';
      const billable = rawData.billable !== undefined ? Boolean(rawData.billable) : authMode === 'api_key';
      const source = (rawData.source as string) || 'delegate:external';

      const savingsUsd = !billable ? Number((inputTokens * 0.000003 + outputTokens * 0.000015).toFixed(6)) : 0;

      resolvedUsage = {
        prompt_tokens: inputTokens,
        completion_tokens: outputTokens,
        total_tokens: totalTokens,
        auth_mode: authMode,
        billable: billable,
        source: source,
        estimated_savings_usd: savingsUsd,
      };

      resolvedCostUsd =
        typeof rawData.cost_usd === 'number'
          ? (rawData.cost_usd as number)
          : billable
            ? Number((inputTokens * 0.000003 + outputTokens * 0.000015).toFixed(6))
            : 0;
      resolvedModelName = typeof rawData.model_name === 'string' ? (rawData.model_name as string) : source;
    }

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        state.messages[messageIndex].usage = resolvedUsage;
        if (resolvedCostUsd !== undefined) {
          state.messages[messageIndex].costUsd = resolvedCostUsd;
        }
        if (resolvedModelName) {
          state.messages[messageIndex].modelName = resolvedModelName;
        }
      }
    });

    return done(ctx);
  }

  return null;
}
