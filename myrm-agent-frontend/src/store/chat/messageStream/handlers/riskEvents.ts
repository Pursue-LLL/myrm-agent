/**
 * [INPUT]
 * ../streamContext::StreamCtx (POS: per-SSE-event reducer context)
 * ../../streamErrors::RiskBlockedError (POS: the turn the server refused because a risk rule holds its text)
 * @/services/riskHeldToast::parseRiskRules, showRiskHeldToast (POS: the one notice for a text a risk rule holds)
 *
 * [OUTPUT]
 * riskEvents: RISK_BLOCKED SSE handler. The server names the rules that held the message; the notice is worded in the
 * user's language by the shared toast, then the turn is refused with `RiskBlockedError` so the send reports that the
 * server never took it and the composer gets the text back.
 *
 * [POS]
 * Chat SSE event handler slice for the server-side input risk gate.
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { AgentEventType } from '../../types/agentStream/part1';
import { RiskBlockedError } from '../../streamErrors';
import { parseRiskRules, showRiskHeldToast } from '@/services/riskHeldToast';

export async function riskEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;

  if (data.type === AgentEventType.RISK_BLOCKED) {
    const payload = data.data as { rules?: unknown } | undefined;
    showRiskHeldToast(parseRiskRules(payload?.rules));

    actions.setLoading(false);
    throw new RiskBlockedError();
  }

  return null;
}
