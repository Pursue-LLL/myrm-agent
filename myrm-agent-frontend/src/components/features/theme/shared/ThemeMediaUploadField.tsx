'use client';

import { useCallback, useRef, useState } from 'react';
import { ImageIcon, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { validateThemeBackgroundFile, type ThemeBackgroundValidationError } from '@/theme-engine';
import { resolveThemeAssetUrl } from '@/services/theme-assets/ThemeAssetStore';
import { VideoPosterExtractionError } from '@/services/theme-assets/extractVideoPoster';
import {
  ThemeBackgroundValidationFailedError,
  uploadThemeBackground,
} from '@/services/theme-assets/uploadThemeBackground';

const ACCEPTED_BACKGROUND_TYPES =
  'image/png,image/jpeg,image/webp,video/mp4,.png,.jpg,.jpeg,.webp,.mp4';

const VALIDATION_MESSAGE_KEYS: Record<
  ThemeBackgroundValidationError,
  'backgroundInvalidType' | 'backgroundTooLarge' | 'backgroundEmpty'
> = {
  invalidType: 'backgroundInvalidType',
  tooLarge: 'backgroundTooLarge',
  empty: 'backgroundEmpty',
};

interface ThemeMediaUploadFieldProps {
  disabled?: boolean;
  onUploaded: (payload: {
    assetRef: string;
    mediaKind: 'image' | 'video';
    posterAssetRef?: string | null;
    previewUrl: string | null;
  }) => void;
}

const ThemeMediaUploadField = ({ disabled = false, onUploaded }: ThemeMediaUploadFieldProps) => {
  const t = useTranslations('settings.appearancePanel');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleBackgroundSelected = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) {
        return;
      }
      const validationError = validateThemeBackgroundFile(file);
      if (validationError) {
        toast.error(t(VALIDATION_MESSAGE_KEYS[validationError]));
        return;
      }
      setUploading(true);
      try {
        const { assetRef, mediaKind, posterAssetRef } = await uploadThemeBackground(file);
        const previewUrl = await resolveThemeAssetUrl(
          mediaKind === 'video' ? (posterAssetRef ?? assetRef) : assetRef,
        );
        onUploaded({ assetRef, mediaKind, posterAssetRef, previewUrl });
      } catch (error) {
        const message =
          error instanceof ThemeBackgroundValidationFailedError
            ? t(VALIDATION_MESSAGE_KEYS[error.code])
            : error instanceof VideoPosterExtractionError
              ? t('backgroundPosterFailed')
              : error instanceof Error
                ? error.message
                : t('backgroundUploadFailed');
        toast.error(message);
      } finally {
        setUploading(false);
      }
    },
    [onUploaded, t],
  );

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_BACKGROUND_TYPES}
        className="hidden"
        onChange={(event) => void handleBackgroundSelected(event)}
      />
      <button
        type="button"
        disabled={disabled || uploading}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          'inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-all',
          'border-border bg-secondary/40 text-muted-foreground hover:text-foreground',
          (disabled || uploading) && 'opacity-60 pointer-events-none',
        )}
      >
        {uploading ? (
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
        ) : (
          <ImageIcon className="w-4 h-4" aria-hidden />
        )}
        {t('uploadBackground')}
      </button>
    </>
  );
};

export default ThemeMediaUploadField;
