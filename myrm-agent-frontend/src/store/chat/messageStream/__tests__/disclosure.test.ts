import { describe, expect, it } from 'vitest';

import { applyDisclosureMetadata } from '../disclosure';
import type { Message } from '@/store/chat/types';

const makeMessage = (): Message => ({
  messageId: 'msg-1',
  chatId: 'chat-1',
  content: 'answer',
  role: 'assistant',
  createdAt: new Date('2026-01-02T00:00:00Z'),
});

describe('applyDisclosureMetadata', () => {
  it('maps the evidence tier from the message_end payload', () => {
    const message = makeMessage();

    applyDisclosureMetadata(message, {
      deliverable_tier: { tier: 'VERIFIED', evidence: { verification_count: 2 } },
    });

    expect(message.deliverableTier?.tier).toBe('VERIFIED');
    expect(message.deliverableTier?.evidence?.verification_count).toBe(2);
  });

  it('maps staged deliverable drafts from the message_end payload', () => {
    const message = makeMessage();

    applyDisclosureMetadata(message, {
      staged_artifacts: [{ filename: 'draft.py', relative_path: '.myrm/staged_artifacts/draft.py' }],
    });

    expect(message.stagedArtifacts).toHaveLength(1);
    expect(message.stagedArtifacts?.[0]?.filename).toBe('draft.py');
  });

  it('leaves the message untouched when the payload has no disclosure', () => {
    const message = makeMessage();

    applyDisclosureMetadata(message, { completion_status: 'complete', staged_artifacts: [] });

    expect(message.deliverableTier).toBeUndefined();
    expect(message.stagedArtifacts).toBeUndefined();
  });

  it('ignores malformed values', () => {
    const message = makeMessage();

    applyDisclosureMetadata(message, { deliverable_tier: 'VERIFIED', staged_artifacts: 'draft.py' });

    expect(message.deliverableTier).toBeUndefined();
    expect(message.stagedArtifacts).toBeUndefined();
  });
});
