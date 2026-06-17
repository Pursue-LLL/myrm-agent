import { describe, it, expect } from 'vitest';
import { resolveDeliverySkipReasonKey } from '../cron-utils';

describe('resolveDeliverySkipReasonKey', () => {
  it('maps silent_response', () => {
    expect(resolveDeliverySkipReasonKey('skipped', 'silent_response')).toBe('skipReasonSilentResponse');
  });

  it('maps duplicate_output', () => {
    expect(resolveDeliverySkipReasonKey('skipped', 'duplicate_output')).toBe('skipReasonDuplicateOutput');
  });

  it('maps no_new_content', () => {
    expect(resolveDeliverySkipReasonKey('skipped', 'no_new_content')).toBe('skipReasonNoNewContent');
  });

  it('returns undefined for delivered runs', () => {
    expect(resolveDeliverySkipReasonKey('delivered', 'silent_response')).toBeUndefined();
  });

  it('returns undefined for unknown skip codes', () => {
    expect(resolveDeliverySkipReasonKey('skipped', 'unknown_code')).toBeUndefined();
  });
});
