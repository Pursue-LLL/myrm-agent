import { describe, expect, it } from 'vitest';

import { resolveCompanionFormatLabelKey } from '@/services/companion/companionFormatLabelCore';

describe('resolveCompanionFormatLabelKey', () => {
  it('maps ok codex tier to codex label key', () => {
    expect(
      resolveCompanionFormatLabelKey({
        format_tier: 'ok',
        format_label: 'Format: Codex Standard',
      }),
    ).toBe('gallery.formatCodexStandard');
  });

  it('maps ok legacy tier via label hint', () => {
    expect(
      resolveCompanionFormatLabelKey({
        format_tier: 'ok',
        format_label: 'Format: Legacy Standard',
      }),
    ).toBe('gallery.formatLegacyStandard');
  });

  it('maps warn tier to non-standard key', () => {
    expect(
      resolveCompanionFormatLabelKey({
        format_tier: 'warn',
        format_label: 'Format: Non-standard',
      }),
    ).toBe('gallery.formatNonStandard');
  });

  it('returns null when tier missing', () => {
    expect(resolveCompanionFormatLabelKey({})).toBeNull();
  });
});
