/**
 * discardStreamedDraft — restart-protocol helper that resets the stream-level
 * draft buffers (received text + pending render task) before a recovery re-runs
 * the turn from scratch. Complements clearAssistantDraft (message-level).
 */
import { describe, expect, it, vi } from 'vitest';

import { discardStreamedDraft } from '../messageUtils';

describe('discardStreamedDraft', () => {
  it('clears received message and cancels the pending render task', () => {
    const cancel = vi.fn();
    const ctx = {
      recievedMessage: 'Partial draft ',
      state: { scheduler: { cancel } },
    };

    discardStreamedDraft(ctx);

    expect(ctx.recievedMessage).toBe('');
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it('tolerates a missing scheduler (no render task pending)', () => {
    const ctx = {
      recievedMessage: 'Partial draft ',
      state: {} as { scheduler?: { cancel?: () => void } },
    };

    expect(() => discardStreamedDraft(ctx)).not.toThrow();
    expect(ctx.recievedMessage).toBe('');
  });

  it('tolerates a scheduler without cancel', () => {
    const ctx = {
      recievedMessage: 'Partial draft ',
      state: { scheduler: {} as { cancel?: () => void } },
    };

    expect(() => discardStreamedDraft(ctx)).not.toThrow();
    expect(ctx.recievedMessage).toBe('');
  });
});
