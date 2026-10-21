import { describe, expect, it } from 'vitest';

import {
  PRIOR_CHAT_DRAG_MIME,
  buildPriorChatMention,
  decodePriorChatDragPayload,
  encodePriorChatDragPayload,
} from '../priorChatDrag';

describe('priorChatDrag', () => {
  it('round-trips drag payload', () => {
    const encoded = encodePriorChatDragPayload({ chatId: 'chat-1', title: 'Alpha plan' });
    expect(decodePriorChatDragPayload(encoded)).toEqual({ chatId: 'chat-1', title: 'Alpha plan' });
  });

  it('rejects invalid payload', () => {
    expect(decodePriorChatDragPayload('')).toBeNull();
    expect(decodePriorChatDragPayload('{"title":"x"}')).toBeNull();
  });

  it('builds prior_chat mention', () => {
    const mention = buildPriorChatMention({ chatId: 'chat-2', title: 'Beta' });
    expect(mention.type).toBe('prior_chat');
    expect(mention.label).toBe('@chat:Beta');
    expect(mention.path).toBe('chat-2');
  });

  it('exports stable mime type', () => {
    expect(PRIOR_CHAT_DRAG_MIME).toContain('myrm-prior-chat');
  });
});
