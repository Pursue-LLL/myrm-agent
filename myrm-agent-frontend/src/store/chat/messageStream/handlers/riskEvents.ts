/**
 * [POS]
 * Chat SSE event handler slice (riskEvents).
 * Handles risk_blocked events from the server-side input risk gate.
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import { AgentEventType } from "../../types/agentStream/part1";

interface RiskBlockedPayload {
  message: string;
  rules?: Array<{ rule_id: string; display_name: string; severity: string }>;
}

export async function riskEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;

  if (data.type === AgentEventType.RISK_BLOCKED) {
    const payload = data.data as RiskBlockedPayload | undefined;
    const blockMessage = payload?.message || 'Your message was blocked by risk policy.';

    const { toast } = await import('@/lib/utils/toast');
    toast.error(blockMessage, { duration: 8000 });

    actions.setLoading(false);
    return done(ctx);
  }

  return null;
}
