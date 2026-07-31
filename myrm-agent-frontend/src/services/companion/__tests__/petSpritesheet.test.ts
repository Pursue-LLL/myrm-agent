import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  getApiUrl: (endpoint: string) => `http://localhost:8080/api/v1${endpoint}`,
}));

import {
  companionPetSpritesheetUrl,
  resolveCompanionSpritesheetUrl,
} from '../petSpritesheet';

describe('petSpritesheet', () => {
  it('builds spritesheet URL from pet slug', () => {
    expect(companionPetSpritesheetUrl('nous-girl')).toBe(
      'http://localhost:8080/api/v1/companion/pets/nous-girl/spritesheet',
    );
  });

  it('encodes slug segments in URL', () => {
    expect(companionPetSpritesheetUrl('pet/with space')).toBe(
      'http://localhost:8080/api/v1/companion/pets/pet%2Fwith%20space/spritesheet',
    );
  });

  it('returns null when config is missing slug', () => {
    expect(resolveCompanionSpritesheetUrl(null)).toBeNull();
    expect(resolveCompanionSpritesheetUrl({ petSlug: '' })).toBeNull();
  });

  it('resolves local API URL from sprite config', () => {
    expect(
      resolveCompanionSpritesheetUrl({
        petSlug: 'nous-girl',
        displayName: 'Nous Girl',
        contentSha256: 'abc',
      }),
    ).toBe('http://localhost:8080/api/v1/companion/pets/nous-girl/spritesheet');
  });
});
