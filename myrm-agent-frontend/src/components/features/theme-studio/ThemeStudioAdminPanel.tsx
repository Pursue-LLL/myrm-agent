'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, ShieldCheck } from 'lucide-react';
import { toast } from '@/lib/utils/toast';
import ThemeMarketplaceGateBanner from '@/components/features/theme-studio/ThemeMarketplaceGateBanner';
import { useThemeMarketplaceGate } from '@/components/features/theme-studio/hooks/useThemeMarketplaceGate';
import {
  listAdminThemeCatalog,
  listPendingThemeListings,
  restoreThemeListing,
  reviewThemeListing,
  suspendThemeListing,
  type ThemeMarketplaceListing,
} from '@/services/themeMarketplace';

const MIN_REASON_LENGTH = 2;

type ModerationMode = 'reject' | 'suspend' | 'restore';

const ThemeStudioAdminPanel = () => {
  const t = useTranslations('settings.themeStudio.admin');
  const { gate } = useThemeMarketplaceGate();
  const [visible, setVisible] = useState(false);
  const [pendingItems, setPendingItems] = useState<ThemeMarketplaceListing[]>([]);
  const [catalogItems, setCatalogItems] = useState<ThemeMarketplaceListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [moderation, setModeration] = useState<{
    listingId: string;
    mode: ModerationMode;
  } | null>(null);
  const [moderationReason, setModerationReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pending, catalog] = await Promise.all([
        listPendingThemeListings(),
        listAdminThemeCatalog(),
      ]);
      setPendingItems(pending);
      setCatalogItems(catalog);
      setVisible(true);
    } catch {
      setPendingItems([]);
      setCatalogItems([]);
      setVisible(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (gate !== 'ready') {
      setLoading(false);
      setVisible(false);
      return;
    }
    void load();
  }, [gate, load]);

  const cancelModeration = useCallback(() => {
    setModeration(null);
    setModerationReason('');
  }, []);

  const handleReview = useCallback(
    async (listingId: string, action: 'approve' | 'reject', reason: string) => {
      setBusyId(listingId);
      try {
        await reviewThemeListing(listingId, { action, reason });
        toast.success(action === 'approve' ? t('approved') : t('rejected'));
        if (action === 'reject') {
          cancelModeration();
        }
        await load();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('reviewFailed'));
      } finally {
        setBusyId(null);
      }
    },
    [cancelModeration, load, t],
  );

  const handleCatalogAction = useCallback(
    async (listingId: string, mode: 'suspend' | 'restore', reason: string) => {
      setBusyId(listingId);
      try {
        if (mode === 'suspend') {
          await suspendThemeListing(listingId, reason);
          toast.success(t('suspended'));
        } else {
          await restoreThemeListing(listingId, reason);
          toast.success(t('restored'));
        }
        cancelModeration();
        await load();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('moderationFailed'));
      } finally {
        setBusyId(null);
      }
    },
    [cancelModeration, load, t],
  );

  const startModeration = useCallback((listingId: string, mode: ModerationMode) => {
    setModeration({ listingId, mode });
    setModerationReason('');
  }, []);

  const confirmModeration = useCallback(() => {
    if (!moderation) {
      return;
    }
    const trimmed = moderationReason.trim();
    if (trimmed.length < MIN_REASON_LENGTH) {
      toast.error(t('reasonTooShort'));
      return;
    }
    if (moderation.mode === 'reject') {
      void handleReview(moderation.listingId, 'reject', trimmed);
      return;
    }
    void handleCatalogAction(moderation.listingId, moderation.mode, trimmed);
  }, [handleCatalogAction, handleReview, moderation, moderationReason, t]);

  const renderModerationForm = (listingId: string) => {
    if (moderation?.listingId !== listingId) {
      return null;
    }
    const labelKey =
      moderation.mode === 'reject'
        ? 'rejectReasonLabel'
        : moderation.mode === 'suspend'
          ? 'suspendReasonLabel'
          : 'restoreReasonLabel';
    const placeholderKey =
      moderation.mode === 'reject'
        ? 'rejectReasonPlaceholder'
        : moderation.mode === 'suspend'
          ? 'suspendReasonPlaceholder'
          : 'restoreReasonPlaceholder';
    const confirmKey =
      moderation.mode === 'reject'
        ? 'rejectConfirm'
        : moderation.mode === 'suspend'
          ? 'suspendConfirm'
          : 'restoreConfirm';

    return (
      <div className="space-y-2 border-t border-border/60 pt-2">
        <label
          htmlFor={`moderation-reason-${listingId}`}
          className="block text-xs font-medium text-muted-foreground"
        >
          {t(labelKey)}
        </label>
        <textarea
          id={`moderation-reason-${listingId}`}
          value={moderationReason}
          onChange={(event) => setModerationReason(event.target.value)}
          disabled={busyId === listingId}
          className="min-h-20 w-full rounded-md border border-border/60 bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-primary disabled:opacity-50"
          placeholder={t(placeholderKey)}
        />
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busyId === listingId}
            onClick={confirmModeration}
            className={
              moderation.mode === 'restore'
                ? 'rounded-md bg-primary px-2 py-1 text-xs text-primary-foreground disabled:opacity-50'
                : 'rounded-md bg-destructive px-2 py-1 text-xs text-destructive-foreground disabled:opacity-50'
            }
          >
            {t(confirmKey)}
          </button>
          <button
            type="button"
            disabled={busyId === listingId}
            onClick={cancelModeration}
            className="rounded-md border border-border px-2 py-1 text-xs disabled:opacity-50"
          >
            {t('moderationCancel')}
          </button>
        </div>
      </div>
    );
  };

  if (gate === 'loading') {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-muted/10 p-4 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        {t('loading')}
      </div>
    );
  }

  if (gate === 'needs_auth' || gate === 'offline') {
    return <ThemeMarketplaceGateBanner gate={gate} />;
  }

  if (!loading && !visible) {
    return null;
  }

  return (
    <section className="rounded-xl border border-border/60 bg-muted/10 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          {t('loading')}
        </div>
      ) : (
        <>
          <div className="space-y-2">
            <h4 className="text-xs font-medium text-muted-foreground">{t('pendingSection')}</h4>
            {pendingItems.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('empty')}</p>
            ) : (
              <ul className="space-y-2">
                {pendingItems.map((listing) => (
                  <li
                    key={listing.id}
                    className="flex flex-col gap-2 rounded-lg border border-border/60 bg-background/80 p-3"
                  >
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-sm font-medium text-foreground">{listing.name}</p>
                        <p className="text-xs text-muted-foreground">{listing.slug}</p>
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          disabled={busyId !== null || moderation?.listingId === listing.id}
                          onClick={() => void handleReview(listing.id, 'approve', t('defaultReviewReason'))}
                          className="rounded-md bg-primary px-2 py-1 text-xs text-primary-foreground disabled:opacity-50"
                        >
                          {t('approve')}
                        </button>
                        <button
                          type="button"
                          disabled={busyId !== null}
                          onClick={() => startModeration(listing.id, 'reject')}
                          className="rounded-md border border-border px-2 py-1 text-xs disabled:opacity-50"
                        >
                          {t('reject')}
                        </button>
                      </div>
                    </div>
                    {renderModerationForm(listing.id)}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-2 border-t border-border/60 pt-3">
            <h4 className="text-xs font-medium text-muted-foreground">{t('catalogSection')}</h4>
            {catalogItems.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('catalogEmpty')}</p>
            ) : (
              <ul className="space-y-2">
                {catalogItems.map((listing) => (
                  <li
                    key={listing.id}
                    className="flex flex-col gap-2 rounded-lg border border-border/60 bg-background/80 p-3"
                  >
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-sm font-medium text-foreground">{listing.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {listing.slug} · {t(`status.${listing.status}`)}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        {listing.status === 'published' ? (
                          <button
                            type="button"
                            disabled={busyId !== null}
                            onClick={() => startModeration(listing.id, 'suspend')}
                            className="rounded-md border border-destructive/40 px-2 py-1 text-xs text-destructive disabled:opacity-50"
                          >
                            {t('suspend')}
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={busyId !== null}
                            onClick={() => startModeration(listing.id, 'restore')}
                            className="rounded-md border border-border px-2 py-1 text-xs disabled:opacity-50"
                          >
                            {t('restore')}
                          </button>
                        )}
                      </div>
                    </div>
                    {renderModerationForm(listing.id)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
};

export default ThemeStudioAdminPanel;
