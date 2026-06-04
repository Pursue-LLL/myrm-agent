/**
 * [INPUT]
 * @/store/chat/types::AgentStreamEvent (POS: Chat SSE event types)
 * ./types::StreamHandlerState, StreamHandlerActions (POS: Stream handler contracts)
 * ./streamContext::StreamCtx (POS: per-event handler context)
 * ./handlers::STREAM_EVENT_HANDLERS (POS: ordered SSE event handler slices)
 *
 * [OUTPUT]
 * handleMessageStream: dispatches Agent SSE events to handler slices
 *
 * [POS]
 * Chat stream reducer entry. Maps runtime events into message state via handlers/*.
 */

import type { Source, File, AgentStreamEvent } from '@/store/chat/types';
import type { StreamHandlerActions, StreamHandlerState } from './types';
import type { StreamCtx } from './streamContext';
import { done } from './streamContext';
import { STREAM_EVENT_HANDLERS } from './handlers';

export type { StreamHandlerActions, StreamHandlerState, StreamMutableState } from './types';

export const handleMessageStream = async (
  data: AgentStreamEvent,
  input: string,
  sources: Source[] | undefined,
  added: boolean,
  recievedMessage: string,
  state: StreamHandlerState,
  actions: StreamHandlerActions,
  _files: File[] = [],
): Promise<{
  added: boolean;
  recievedMessage: string;
}> => {
  if (data && typeof data === 'object' && 'mascot_status' in data && typeof data.mascot_status === 'string') {
    try {
      const companionStore = (await import('@/store/useCompanionStore')).default;
      companionStore.getState().setMascotStatus(data.mascot_status);
    } catch {
      // safe fallback
    }
  }

  const ctx: StreamCtx = {
    data,
    input,
    sources,
    added,
    recievedMessage,
    state,
    actions,
    files: _files,
  };

  for (const handler of STREAM_EVENT_HANDLERS) {
    const result = await handler(ctx);
    if (result !== null) {
      return result;
    }
  }

  return done(ctx);
};
