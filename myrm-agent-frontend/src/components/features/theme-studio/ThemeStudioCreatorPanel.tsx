'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, Upload } from 'lucide-react';
import { toast } from '@/lib/utils/toast';
import ThemeMarketplaceGateBanner from '@/components/features/theme-studio/ThemeMarketplaceGateBanner';
import { useThemeMarketplaceGate } from '@/components/features/theme-studio/hooks/useThemeMarketplaceGate';
import ThemePackageImportPreview from '@/components/features/theme/ThemePackageImportPreview';
import {
  inspectThemePackage,
  type ThemePackageInspectResult,
} from '@/services/theme-packages/inspectThemePackage';
import {
  fetchCreatorThemeStats,
  listMyThemeListings,
  submitThemeListing,
  type ThemeMarketplaceListing,
} from '@/services/themeMarketplace';

const CREATOR_LISTING_STATUSES = [
  'pending',
  'pending_review',
  'published',
  'rejected',
  'suspended',
  'draft',
] as const;

type CreatorListingStatus = (typeof CREATOR_LISTING_STATUSES)[number];

const ThemeStudioCreatorPanel = () => {
  const t = useTranslations('settings.themeStudio.creator');
  const { gate } = useThemeMarketplaceGate();
  const [mine, setMine] = useState<ThemeMarketplaceListing[]>([]);
  const [totalEarnedCents, setTotalEarnedCents] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [inspecting, setInspecting] = useState(false);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [tagline, setTagline] = useState('');
  const [description, setDescription] = useState('');
  const [priceCents, setPriceCents] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [packageInspect, setPackageInspect] = useState<ThemePackageInspectResult | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [listings, stats] = await Promise.all([
        listMyThemeListings(),
        fetchCreatorThemeStats(),
      ]);
      setMine(listings);
      setTotalEarnedCents(stats.totalEarnedCents);
    } catch {
      setMine([]);
      setTotalEarnedCents(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (gate !== 'ready') {
      setLoading(false);
      return;
    }
    void load();
  }, [gate, load]);

  const resetForm = useCallback(() => {
    setFile(null);
    setPackageInspect(null);
    setPreviewOpen(false);
    setName('');
    setSlug('');
    setTagline('');
    setDescription('');
    setPriceCents(0);
  }, []);

  const runSubmit = useCallback(async () => {
    if (!file || !name.trim()) {
      return;
    }
    setSubmitting(true);
    try {
      await submitThemeListing({
        file,
        name: name.trim(),
        slug: slug.trim() || name.trim(),
        tagline: tagline.trim(),
        description: description.trim(),
        priceCents,
      });
      toast.success(t('submitted'));
      resetForm();
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('errors.submitFailed'));
    } finally {
      setSubmitting(false);
    }
  }, [description, file, load, name, priceCents, resetForm, slug, t, tagline]);

  const handleFileSelected = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const selected = event.target.files?.[0] ?? null;
      event.target.value = '';
      setFile(selected);
      setPackageInspect(null);
      if (!selected) {
        return;
      }
      setInspecting(true);
      try {
        const inspect = await inspectThemePackage(selected);
        setPackageInspect(inspect);
        setPreviewOpen(true);
        if (!name.trim() && inspect.name) {
          setName(inspect.name);
        }
      } catch (error) {
        setFile(null);
        toast.error(error instanceof Error ? error.message : t('errors.inspectFailed'));
      } finally {
        setInspecting(false);
      }
    },
    [name, t],
  );

  const handleSubmit = useCallback(async () => {
    if (!file || !name.trim()) {
      toast.error(t('errors.missingFields'));
      return;
    }
    if (!packageInspect) {
      setInspecting(true);
      try {
        const inspect = await inspectThemePackage(file);
        setPackageInspect(inspect);
        setPreviewOpen(true);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('errors.inspectFailed'));
      } finally {
        setInspecting(false);
      }
      return;
    }
    setPreviewOpen(true);
  }, [file, name, packageInspect, t]);

  const handleConfirmPreview = useCallback(() => {
    if (!packageInspect?.canImport) {
      toast.error(t('errors.inspectFailed'));
      return;
    }
    if (!name.trim()) {
      toast.error(t('errors.missingFields'));
      return;
    }
    setPreviewOpen(false);
    void runSubmit();
  }, [name, packageInspect, runSubmit, t]);

  const formatStatus = useCallback(
    (status: string) => {
      if ((CREATOR_LISTING_STATUSES as readonly string[]).includes(status)) {
        return t(`status.${status as CreatorListingStatus}`);
      }
      return status;
    },
    [t],
  );

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

  const busy = submitting || inspecting;

  return (
    <>
      <section className="rounded-xl border border-border/60 bg-muted/10 p-4 space-y-4">
        <div className="flex items-center gap-2">
          <Upload className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
        </div>
        <p className="text-xs text-muted-foreground">{t('subtitle')}</p>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span className="text-muted-foreground">{t('fields.name')}</span>
            <input
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-muted-foreground">{t('fields.slug')}</span>
            <input
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs sm:col-span-2">
            <span className="text-muted-foreground">{t('fields.tagline')}</span>
            <input
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={tagline}
              onChange={(event) => setTagline(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs sm:col-span-2">
            <span className="text-muted-foreground">{t('fields.description')}</span>
            <textarea
              className="w-full min-h-16 rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-muted-foreground">{t('fields.priceCents')}</span>
            <input
              type="number"
              min={0}
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={priceCents}
              onChange={(event) => setPriceCents(Number(event.target.value) || 0)}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-muted-foreground">{t('fields.package')}</span>
            <input
              type="file"
              accept=".myrmtheme,application/zip"
              className="w-full text-xs"
              disabled={busy}
              onChange={(event) => void handleFileSelected(event)}
            />
          </label>
        </div>

        <button
          type="button"
          disabled={busy}
          onClick={() => void handleSubmit()}
          className="rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:opacity-50"
        >
          {submitting ? t('submitting') : inspecting ? t('inspecting') : t('submit')}
        </button>

        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-medium text-foreground">{t('mineTitle')}</p>
            <p className="text-xs text-muted-foreground">
              {t('totalEarned', { amount: (totalEarnedCents / 100).toFixed(2) })}
            </p>
          </div>
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              {t('loading')}
            </div>
          ) : mine.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t('mineEmpty')}</p>
          ) : (
            <ul className="space-y-2 text-xs text-muted-foreground">
              {mine.map((row) => (
                <li
                  key={row.id}
                  className="rounded-md border border-border/50 bg-background/60 px-2 py-1.5 space-y-1"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-foreground font-medium">{row.name}</span>
                    <span className="shrink-0">{formatStatus(row.status)}</span>
                  </div>
                  <p>{t('installCount', { count: row.installCount })}</p>
                  {row.status === 'rejected' && row.reviewReason ? (
                    <p className="text-destructive/90">{row.reviewReason}</p>
                  ) : null}
                  {row.status === 'suspended' && row.reviewReason ? (
                    <p className="text-destructive/90">{row.reviewReason}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <ThemePackageImportPreview
        open={previewOpen}
        inspect={packageInspect}
        busy={submitting}
        onClose={() => setPreviewOpen(false)}
        onConfirm={handleConfirmPreview}
        translationNamespace="settings.themeStudio.creator.preview"
      />
    </>
  );
};

export default ThemeStudioCreatorPanel;
