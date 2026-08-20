'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Loader2, Search, Store } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import useConfigStore from '@/store/useConfigStore';
import {
  acquireThemeListing,
  checkoutThemeListing,
  downloadThemePackage,
  installThemeFromMarketplace,
  issueThemeDownloadToken,
  listThemeMarketplace,
  recordThemeInstall,
  waitForThemeListingOwnership,
  type ThemeMarketplaceListing,
} from '@/services/themeMarketplace';
import ThemeMarketplaceGateBanner from '@/components/features/theme-studio/ThemeMarketplaceGateBanner';
import { useThemeMarketplaceGate } from '@/components/features/theme-studio/hooks/useThemeMarketplaceGate';
import { EMPTY_THEME_PROFILES, type ThemeProfileRecipe } from '@/theme-engine';
import { mergeProfileIntoLibrary } from '@/components/features/theme-studio/studio-profile';
import ThemeStudioMarketplacePreviewDialog from '@/components/features/theme-studio/ThemeStudioMarketplacePreviewDialog';
import { filterAndSortGalleryItems, type GallerySort } from '@/components/features/theme-studio/gallery-listing-filter';

type GalleryTab = 'official' | 'community' | 'owned';

type PurchaseReturnPhase = 'idle' | 'completing' | 'failed';

async function recordThemeInstallWithRetry(listingId: string, warnMessage: string): Promise<void> {
  try {
    await recordThemeInstall(listingId);
    return;
  } catch {
    try {
      await recordThemeInstall(listingId);
    } catch (secondError) {
      console.warn('Theme install succeeded locally but CP install counter failed:', secondError);
      toast.warning(warnMessage);
    }
  }
}

const ThemeStudioGalleryPanel = () => {
  const t = useTranslations('settings.themeStudio.gallery');
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const purchaseReturnHandled = useRef(false);

  const [tab, setTab] = useState<GalleryTab>('official');
  const [searchQuery, setSearchQuery] = useState('');
  const [sort, setSort] = useState<GallerySort>('latest');
  const [items, setItems] = useState<ThemeMarketplaceListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [previewListing, setPreviewListing] = useState<ThemeMarketplaceListing | null>(null);
  const [purchaseReturn, setPurchaseReturn] = useState<{
    phase: PurchaseReturnPhase;
    listingId: string | null;
  }>({ phase: 'idle', listingId: null });

  const themeProfiles = useConfigStore((state) => state.personalSettings?.themeProfiles ?? EMPTY_THEME_PROFILES);
  const updatePersonalSettings = useConfigStore((state) => state.updatePersonalSettings);
  const { gate } = useThemeMarketplaceGate();

  const load = useCallback(
    async (tabOverride?: GalleryTab) => {
      const activeTab = tabOverride ?? tab;
      setLoading(true);
      try {
        const rows = await listThemeMarketplace(
          activeTab === 'community'
            ? { origin: 'community' }
            : activeTab === 'official'
              ? { origin: 'official' }
              : undefined,
        );
        const filtered = activeTab === 'owned' ? rows.filter((row) => row.isOwned) : rows;
        setItems(filtered);
      } catch {
        setItems([]);
      } finally {
        setLoading(false);
      }
    },
    [tab],
  );

  useEffect(() => {
    if (gate !== 'ready') {
      setLoading(false);
      return;
    }
    void load();
  }, [gate, load]);

  const runInstall = useCallback(
    async (listing: ThemeMarketplaceListing, refreshTab?: GalleryTab) => {
      setInstallingId(listing.id);
      try {
        if (!listing.isOwned && listing.priceCents === 0) {
          await acquireThemeListing(listing.id);
        }
        const token = await issueThemeDownloadToken(listing.id);
        const blob = await downloadThemePackage(listing.id, token);
        const existingIds = themeProfiles.map((profile) => profile.id);
        const profileRaw = await installThemeFromMarketplace({
          listingId: listing.id,
          listingOrigin: listing.origin,
          token,
          packageBlob: blob,
          setActive: true,
          existingProfileIds: existingIds,
        });
        const installed = profileRaw as unknown as ThemeProfileRecipe;
        if (installed?.id) {
          await updatePersonalSettings({
            themeProfiles: mergeProfileIntoLibrary(themeProfiles, installed),
            activeThemeProfileId: installed.id,
          });
        }
        await recordThemeInstallWithRetry(listing.id, t('recordInstallWarn'));
        await load(refreshTab);
        toast.success(t('installed'));
      } catch (error) {
        const message = error instanceof Error ? error.message : t('installFailed');
        toast.error(message);
      } finally {
        setInstallingId(null);
        setPreviewListing(null);
      }
    },
    [load, t, themeProfiles, updatePersonalSettings],
  );

  const resetGalleryFilters = useCallback(() => {
    setSearchQuery('');
    setSort('latest');
  }, []);

  useEffect(() => {
    if (gate !== 'ready' || purchaseReturnHandled.current) {
      return;
    }
    const listingId = searchParams.get('theme_purchased')?.trim();
    if (!listingId) {
      return;
    }
    purchaseReturnHandled.current = true;

    const params = new URLSearchParams(searchParams.toString());
    params.delete('theme_purchased');
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });

    void (async () => {
      flushSync(() => {
        setTab('owned');
        resetGalleryFilters();
      });
      setPurchaseReturn({ phase: 'completing', listingId });
      try {
        const listing = await waitForThemeListingOwnership(listingId);
        await runInstall(listing, 'owned');
        setPurchaseReturn({ phase: 'idle', listingId: null });
      } catch {
        setPurchaseReturn({ phase: 'failed', listingId });
        toast.error(t('purchaseReturnFailed'));
      }
    })();
  }, [gate, pathname, resetGalleryFilters, router, runInstall, searchParams, t]);

  const handleRetryPurchaseInstall = useCallback(async () => {
    const listingId = purchaseReturn.listingId;
    if (!listingId) {
      return;
    }
    flushSync(() => {
      setTab('owned');
      resetGalleryFilters();
    });
    setPurchaseReturn({ phase: 'completing', listingId });
    try {
      const listing = await waitForThemeListingOwnership(listingId, { attempts: 5, delayMs: 2000 });
      await runInstall(listing, 'owned');
      setPurchaseReturn({ phase: 'idle', listingId: null });
    } catch {
      setPurchaseReturn({ phase: 'failed', listingId });
      toast.error(t('purchaseReturnFailed'));
    }
  }, [purchaseReturn.listingId, resetGalleryFilters, runInstall, t]);

  const tabs = useMemo(
    () =>
      [
        { id: 'official' as const, label: t('tabs.official') },
        { id: 'community' as const, label: t('tabs.community') },
        { id: 'owned' as const, label: t('tabs.owned') },
      ] as const,
    [t],
  );

  const displayItems = useMemo(() => filterAndSortGalleryItems(items, searchQuery, sort), [items, searchQuery, sort]);

  const handleTabChange = useCallback(
    (nextTab: GalleryTab) => {
      setTab(nextTab);
      resetGalleryFilters();
    },
    [resetGalleryFilters],
  );

  const handlePurchase = useCallback(
    async (listing: ThemeMarketplaceListing) => {
      setInstallingId(listing.id);
      try {
        const { checkoutUrl } = await checkoutThemeListing(listing.id);
        window.location.href = checkoutUrl;
      } catch (error) {
        const message = error instanceof Error ? error.message : t('purchaseFailed');
        toast.error(message);
        setInstallingId(null);
      }
    },
    [t],
  );

  const handlePrimaryAction = useCallback(
    (listing: ThemeMarketplaceListing) => {
      if (listing.priceCents > 0 && !listing.isOwned) {
        void handlePurchase(listing);
        return;
      }
      setPreviewListing(listing);
    },
    [handlePurchase],
  );

  if (gate === 'loading') {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-muted/10 p-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('loading')}
      </div>
    );
  }

  if (gate === 'needs_auth' || gate === 'offline') {
    return <ThemeMarketplaceGateBanner gate={gate} />;
  }

  return (
    <>
      <section className="rounded-xl border border-border/60 bg-muted/10 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Store className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
        </div>
        <p className="text-xs text-muted-foreground">{t('subtitle')}</p>

        {purchaseReturn.phase === 'completing' ? (
          <div
            className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-foreground"
            role="status"
          >
            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
            <span>{t('purchaseCompleting')}</span>
          </div>
        ) : null}

        {purchaseReturn.phase === 'failed' && purchaseReturn.listingId ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs space-y-2">
            <p className="text-foreground">{t('purchaseReturnFailed')}</p>
            <button
              type="button"
              onClick={() => void handleRetryPurchaseInstall()}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
            >
              {t('purchaseRetryOwned')}
            </button>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {tabs.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => handleTabChange(entry.id)}
              className={cn(
                'rounded-full px-3 py-1 text-xs border',
                tab === entry.id
                  ? 'border-primary bg-primary/10 text-foreground'
                  : 'border-border text-muted-foreground',
              )}
            >
              {entry.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <label className="relative flex-1">
            <span className="sr-only">{t('searchLabel')}</span>
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={t('searchPlaceholder')}
              className="w-full rounded-md border border-border/60 bg-background py-2 pl-8 pr-3 text-sm outline-none transition-colors focus:border-primary"
            />
          </label>
          <label className="flex items-center gap-2 sm:w-40">
            <span className="sr-only">{t('sortLabel')}</span>
            <select
              value={sort}
              onChange={(event) => setSort(event.target.value as GallerySort)}
              className="w-full rounded-md border border-border/60 bg-background px-2 py-2 text-sm outline-none transition-colors focus:border-primary"
            >
              <option value="latest">{t('sort.latest')}</option>
              <option value="popular">{t('sort.popular')}</option>
              <option value="price">{t('sort.price')}</option>
            </select>
          </label>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-6 justify-center">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('loading')}
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">{t('empty')}</p>
        ) : displayItems.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">{t('searchEmpty')}</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {displayItems.map((listing) => (
              <li key={listing.id} className="rounded-lg border border-border/60 bg-background/80 p-3 space-y-2">
                {listing.previewThumbnail ? (
                  <div
                    className="aspect-video w-full rounded-md border border-border/50 bg-muted bg-cover bg-center"
                    style={{ backgroundImage: `url(${listing.previewThumbnail})` }}
                    role="img"
                    aria-label={listing.name}
                  />
                ) : null}
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-foreground">{listing.name}</p>
                    {listing.tagline ? (
                      <p className="text-xs text-muted-foreground line-clamp-2">{listing.tagline}</p>
                    ) : null}
                  </div>
                  <span className="text-xs text-muted-foreground shrink-0">
                    {listing.priceCents > 0
                      ? t('pricePaid', { cents: (listing.priceCents / 100).toFixed(2) })
                      : t('priceFree')}
                  </span>
                </div>
                <button
                  type="button"
                  disabled={installingId === listing.id}
                  onClick={() => handlePrimaryAction(listing)}
                  className="w-full rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
                >
                  {installingId === listing.id ? (
                    <span className="inline-flex items-center gap-1 justify-center">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      {listing.priceCents > 0 && !listing.isOwned ? t('purchasing') : t('installing')}
                    </span>
                  ) : listing.priceCents > 0 && !listing.isOwned ? (
                    t('purchase')
                  ) : listing.isOwned ? (
                    t('install')
                  ) : (
                    t('previewInstall')
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ThemeStudioMarketplacePreviewDialog
        open={previewListing !== null}
        listing={previewListing}
        busy={installingId !== null}
        onClose={() => setPreviewListing(null)}
        onConfirm={() => {
          if (previewListing) {
            void runInstall(previewListing);
          }
        }}
      />
    </>
  );
};

export default ThemeStudioGalleryPanel;
