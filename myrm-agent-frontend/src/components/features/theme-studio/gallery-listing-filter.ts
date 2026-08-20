import type { ThemeMarketplaceListing } from '@/services/themeMarketplace';

export type GallerySort = 'latest' | 'popular' | 'price';

export function filterAndSortGalleryItems(
  items: ThemeMarketplaceListing[],
  searchQuery: string,
  sort: GallerySort,
): ThemeMarketplaceListing[] {
  const needle = searchQuery.trim().toLowerCase();
  const filtered = needle
    ? items.filter((listing) => `${listing.name} ${listing.tagline} ${listing.slug}`.toLowerCase().includes(needle))
    : items;

  return [...filtered].sort((left, right) => {
    if (sort === 'popular') {
      return right.installCount - left.installCount;
    }
    if (sort === 'price') {
      return left.priceCents - right.priceCents;
    }
    const leftPublished = left.publishedAt ?? 0;
    const rightPublished = right.publishedAt ?? 0;
    return rightPublished - leftPublished;
  });
}
