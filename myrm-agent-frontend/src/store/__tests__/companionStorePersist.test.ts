import { describe, expect, it } from 'vitest';

import { sanitizePersistedSpriteState } from '../useCompanionStore';

describe('sanitizePersistedSpriteState', () => {
  it('clears legacy sheetUrl-only persisted config', () => {
    expect(
      sanitizePersistedSpriteState({ sheetUrl: 'https://petdex.dev/x.webp', name: 'nous-girl' }, true),
    ).toEqual({ spriteConfig: null, spriteEnabled: false });
  });

  it('keeps valid petSlug config', () => {
    expect(
      sanitizePersistedSpriteState(
        { petSlug: 'nous-girl', displayName: 'Nous Girl', contentSha256: 'abc' },
        true,
      ),
    ).toEqual({
      spriteConfig: {
        petSlug: 'nous-girl',
        displayName: 'Nous Girl',
        contentSha256: 'abc',
      },
      spriteEnabled: true,
    });
  });
});
