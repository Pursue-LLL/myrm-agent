import { describe, expect, it } from 'vitest';

import {
  rankManifestPets,
  type ManifestPet,
} from '@/components/features/companion/petGalleryManifest';

describe('rankManifestPets', () => {
  const pets: ManifestPet[] = [
    {
      slug: 'community-pet',
      displayName: 'Community',
      kind: 'pet',
      spritesheetUrl: 'https://assets.petdex.dev/pets/community/spritesheet.webp',
      curated: false,
    },
    {
      slug: 'nous-girl',
      displayName: 'Nous Girl',
      kind: 'pet',
      spritesheetUrl: 'https://assets.petdex.dev/curated/nous-girl/spritesheet.webp',
      curated: true,
    },
  ];

  it('ranks curated pets before community pets', () => {
    const ranked = rankManifestPets(pets);
    expect(ranked[0]?.slug).toBe('nous-girl');
  });

  it('ranks installed pets higher among non-curated pets', () => {
    const communityOnly: ManifestPet[] = [
      {
        slug: 'pet-a',
        displayName: 'A',
        kind: 'pet',
        spritesheetUrl: 'https://assets.petdex.dev/pets/a/spritesheet.webp',
        curated: false,
      },
      {
        slug: 'pet-b',
        displayName: 'B',
        kind: 'pet',
        spritesheetUrl: 'https://assets.petdex.dev/pets/b/spritesheet.webp',
        curated: false,
      },
    ];
    const ranked = rankManifestPets(communityOnly, {
      installedSlugs: new Set(['pet-b']),
    });
    expect(ranked[0]?.slug).toBe('pet-b');
  });
});
