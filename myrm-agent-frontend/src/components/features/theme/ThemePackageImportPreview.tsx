'use client';

import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import type { ThemePackageInspectResult } from '@/services/theme-packages/inspectThemePackage';

interface ThemePackageImportPreviewProps {
  open: boolean;
  inspect: ThemePackageInspectResult | null;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
  translationNamespace?: 'settings.appearancePanel' | 'settings.themeStudio.creator.preview';
}

const ThemePackageImportPreview = ({
  open,
  inspect,
  busy,
  onClose,
  onConfirm,
  translationNamespace = 'settings.appearancePanel',
}: ThemePackageImportPreviewProps) => {
  const t = useTranslations(translationNamespace);

  if (!inspect) {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('packageImportTitle')}</DialogTitle>
          <DialogDescription>{inspect.name}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {(inspect.heroThumbnailBase64 ?? inspect.previewThumbnailBase64) ? (
            <div
              className="relative aspect-video w-full overflow-hidden rounded-lg border border-border bg-muted"
              style={{
                backgroundImage: `url(${inspect.heroThumbnailBase64 ?? inspect.previewThumbnailBase64})`,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
              }}
              role="img"
              aria-label={t('packageHeroPreview')}
            />
          ) : null}

          {inspect.tagline ? (
            <p className="text-sm text-foreground/90">{inspect.tagline}</p>
          ) : null}

          {inspect.author ? (
            <p className="text-xs text-muted-foreground">{inspect.author}</p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span
              className="inline-block h-4 w-4 rounded-full ring-1 ring-black/10 dark:ring-white/10"
              style={{ backgroundColor: inspect.primaryLight }}
              aria-hidden
            />
            <span>{inspect.layoutId}</span>
            <span>·</span>
            <span>{inspect.fontId}</span>
            <span>·</span>
            <span>{Math.round(inspect.wash * 100)}% {t('backgroundWash').toLowerCase()}</span>
          </div>

          {inspect.description ? (
            <p className="text-sm text-muted-foreground">{inspect.description}</p>
          ) : null}

          {inspect.warnings.length > 0 ? (
            <ul className="space-y-1 text-xs text-amber-600 dark:text-amber-400">
              {inspect.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}

          {inspect.signatureStatus !== 'verified' ? (
            <p className="text-xs text-muted-foreground">{t('packageUnsignedHint')}</p>
          ) : null}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
            {t('packageCancel')}
          </Button>
          <Button type="button" onClick={onConfirm} disabled={busy || !inspect.canImport}>
            {t('packageApply')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ThemePackageImportPreview;
