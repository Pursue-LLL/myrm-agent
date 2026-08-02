import { describe, expect, it } from 'vitest';

import {
  filterAndSortGalleryItems,
  type GallerySort,
} from '@/components/features/theme-studio/gallery-listing-filter';
import type { ThemeMarketplaceListing } from '@/services/themeMarketplace';

function listing(
  overrides: Partial<ThemeMarketplaceListing> & Pick<ThemeMarketplaceListing, 'id' | 'name'>,
): ThemeMarketplaceListing {
  return {
    slug: overrides.slug ?? overrides.name.toLowerCase(),
    tagline: '',
    description: '',
    creatorUserId: 'user-1',
    origin: 'official',
    layoutId: 'chat-first',
    mediaKind: 'none',
    priceCents: 0,
    vipOnly: false,
    status: 'published',
    packageSha256: 'a'.repeat(64),
    previewThumbnail: null,
    installCount: 0,
    publishedAt: 1,
    isOwned: false,
    ...overrides,
  };
}

describe('filterAndSortGalleryItems', () => {
  const rows = [
    listing({ id: 'a', name: 'Neon Night', tagline: 'Cyber glow', installCount: 10, priceCents: 0, publishedAt: 3 }),
    listing({ id: 'b', name: 'Forest Calm', tagline: 'Green focus', installCount: 2, priceCents: 499, publishedAt: 1 }),
    listing({ id: 'c', name: 'Ocean Blue', tagline: 'Deep sea', installCount: 5, priceCents: 99, publishedAt: 2 }),
  ];

  it('filters by name and tagline', () => {
    const result = filterAndSortGalleryItems(rows, 'cyber', 'latest');
    expect(result.map((row) => row.id)).toEqual(['a']);
  });

  it('sorts by popularity', () => {
    const result = filterAndSortGalleryItems(rows, '', 'popular' satisfies GallerySort);
    expect(result.map((row) => row.id)).toEqual(['a', 'c', 'b']);
  });

  it('sorts by price ascending', () => {
    const result = filterAndSortGalleryItems(rows, '', 'price');
    expect(result.map((row) => row.id)).toEqual(['a', 'c', 'b']);
  });
});
