import { describe, expect, it } from 'vitest';
import { parseIntentUrl } from './schema';

describe('parseIntentUrl', () => {
  it('parses myrmagent quick ask intent', () => {
    const intent = parseIntentUrl('myrmagent://ask?text=hello');
    expect(intent).toEqual({
      scheme: 'myrmagent',
      action: 'ask',
      text: 'hello',
    });
  });

  it('parses web quick ask intent route', () => {
    const intent = parseIntentUrl('http://127.0.0.1:3000/intent/ask?text=route%20check');
    expect(intent).toEqual({
      scheme: 'http',
      action: 'ask',
      text: 'route check',
    });
  });

  it('parses web chat intent route', () => {
    const intent = parseIntentUrl('https://app.myrmagent.ai/intent/chat/chat-123');
    expect(intent).toEqual({
      scheme: 'https',
      action: 'chat',
      id: 'chat-123',
    });
  });

  it('throws when path is not an intent route', () => {
    expect(() => parseIntentUrl('https://app.myrmagent.ai/chat/chat-123')).toThrow();
  });

  it('throws for unsupported web intent action names', () => {
    expect(() => parseIntentUrl('https://app.myrmagent.ai/intent/asking?text=hello')).toThrow();
  });
});
