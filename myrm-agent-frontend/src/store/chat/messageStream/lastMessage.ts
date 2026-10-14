/**
 * [INPUT]
 * ./types::StreamHandlerActions (POS: Stream action contract)
 * immer::current, isDraft (POS: Plain copy of a draft)
 *
 * [OUTPUT]
 * readLastMessage: the chat's current last message, read through the stream's own setMessages
 *
 * [POS]
 * `state.messages` of a stream is the snapshot taken when the stream opened, so it never holds the message the turn
 * produced. `setMessages` is the only live view of message state a stream has; follow-up suggestions need the finished
 * turn's message after the write, so they read it here. The copy stays valid after the draft it came from is closed.
 */

import { current, isDraft } from 'immer';
import type { Message } from '@/store/chat/types';
import type { StreamHandlerActions } from './types';

export function readLastMessage(setMessages: StreamHandlerActions['setMessages']): Message | undefined {
  let last: Message | undefined;
  setMessages((live) => {
    const message = live.messages[live.messages.length - 1];
    last = message !== undefined && isDraft(message) ? current(message) : message;
  });
  return last;
}
