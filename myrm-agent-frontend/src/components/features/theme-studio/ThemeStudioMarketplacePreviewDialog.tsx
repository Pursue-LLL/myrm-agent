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
import type { ThemeMarketplaceListing } from '@/services/themeMarketplace';

interface ThemeStudioMarketplacePreviewDialogProps {
  open: boolean;
  listing: ThemeMarketplaceListing | null;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

const ThemeStudioMarketplacePreviewDialog = ({
  open,
  listing,
  busy,
  onClose,
  onConfirm,
}: ThemeStudioMarketplacePreviewDialogProps) => {
  const t = useTranslations('settings.themeStudio.gallery');

  if (!listing) {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('previewTitle')}</DialogTitle>
          <DialogDescription>{listing.name}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {listing.previewThumbnail ? (
            <div
              className="aspect-video w-full rounded-lg border border-border bg-muted bg-cover bg-center"
              style={{ backgroundImage: `url(${listing.previewThumbnail})` }}
              role="img"
              aria-label={listing.name}
            />
          ) : null}
          {listing.tagline ? <p className="text-sm text-foreground/90">{listing.tagline}</p> : null}
          {listing.description ? (
            <p className="text-sm text-muted-foreground line-clamp-4">{listing.description}</p>
          ) : null}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
            {t('previewCancel')}
          </Button>
          <Button type="button" onClick={onConfirm} disabled={busy}>
            {t('previewConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ThemeStudioMarketplacePreviewDialog;
