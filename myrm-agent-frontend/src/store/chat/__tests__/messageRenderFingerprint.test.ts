import { describe, expect, it } from 'vitest';

import { buildMessageRenderFingerprint } from '@/store/chat/messageRenderFingerprint';

describe('buildMessageRenderFingerprint', () => {
  it('changes when sources arrive without content length change', () => {
    const base = [{ messageId: 'm1', content: 'answer【1】', sources: undefined }];
    const withSources = [{ messageId: 'm1', content: 'answer【1】', sources: [{ index: 1 }] }];
    expect(buildMessageRenderFingerprint(base)).not.toBe(buildMessageRenderFingerprint(withSources));
  });

  it('is stable when neither content nor sources change', () => {
    const messages = [{ messageId: 'm1', content: 'hello', sources: [{ index: 1 }] }];
    expect(buildMessageRenderFingerprint(messages)).toBe(buildMessageRenderFingerprint([...messages]));
  });
});
