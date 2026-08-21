/**
 * [INPUT]
 * ./types::StreamHandlerState, StreamHandlerActions (POS: stream handler contracts)
 * @/store/chat/types::AgentStreamEvent, File, Source (POS: chat SSE types)
 *
 * [OUTPUT]
 * StreamCtx, StreamTurn, done(): per-event handler context and result helpers
 *
 * [POS]
 * Shared context for messageStream/handlers/* event slices.
 */

import type { Source, File, AgentStreamEvent } from '@/store/chat/types';
import type { StreamHandlerActions, StreamHandlerState } from './types';

export type TurnMeta = {
  routingTier?: 'simple' | 'standard' | 'reasoning' | 'complex' | 'code' | 'long_doc';
  modelTier?: 'weak' | 'medium';
};

export type StreamTurn = {
  added: boolean;
  recievedMessage: string;
  meta?: TurnMeta;
};

export type StreamCtx = {
  data: AgentStreamEvent;
  input: string;
  sources: Source[] | undefined;
  added: boolean;
  recievedMessage: string;
  state: StreamHandlerState;
  actions: StreamHandlerActions;
  files: File[];
  meta?: TurnMeta;
};

export function done(ctx: StreamCtx): StreamTurn {
  return { added: ctx.added, recievedMessage: ctx.recievedMessage, meta: ctx.meta };
}
