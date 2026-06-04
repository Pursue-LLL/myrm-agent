/**
 * [INPUT]
 * ./messageStream/handleMessageStream (POS: Chat SSE reducer implementation)
 * ./messageStream/types (POS: Stream handler type contracts)
 *
 * [OUTPUT]
 * Re-exports handleMessageStream and stream handler types for existing import paths
 *
 * [POS]
 * Stable import path (`@/store/chat/messageStreamHandler`) for chat streaming consumers.
 */

export { handleMessageStream } from './messageStream/handleMessageStream';
export type {
  StreamHandlerActions,
  StreamHandlerState,
  StreamMutableState,
} from './messageStream/types';
