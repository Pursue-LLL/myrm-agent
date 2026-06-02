'use client';

import React, { memo, useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface ImageGenImage {
  url: string;
  mimeType?: string;
}

interface ImageResultCardProps {
  images: ImageGenImage[];
  prompt?: string;
  model?: string;
  size?: string;
  latencyMs?: number;
  referenceImageUrls?: string[];
  onEditRequest?: (imageUrl: string) => void;
  onRegenerate?: () => void;
}

export const ImageResultCard: React.FC<ImageResultCardProps> = memo(
  ({ images, prompt, model, size, latencyMs, referenceImageUrls, onEditRequest, onRegenerate }) => {
    const t = useTranslations('imageGen');
    const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
    const [promptExpanded, setPromptExpanded] = useState(false);
    const [failedIndexes, setFailedIndexes] = useState<Set<number>>(new Set());

    const handleImgError = useCallback((index: number) => {
      setFailedIndexes((prev) => new Set(prev).add(index));
    }, []);

    const handlePreview = useCallback((index: number) => {
      setLightboxIndex(index);
    }, []);

    const closeLightbox = useCallback(() => {
      setLightboxIndex(null);
    }, []);

    const handleDownload = useCallback(async (img: ImageGenImage, index: number) => {
      const ext = img.mimeType?.split('/')[1] || 'png';
      const filename = `generated-${Date.now()}-${index + 1}.${ext}`;
      try {
        const response = await fetch(img.url);
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = blobUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(blobUrl);
      } catch {
        window.open(img.url, '_blank', 'noopener,noreferrer');
      }
    }, []);

    if (images.length === 0) return null;

    const gridCols =
      images.length === 1
        ? 'grid-cols-1 max-w-sm'
        : images.length === 2
          ? 'grid-cols-2 max-w-md'
          : 'grid-cols-3 max-w-lg';

    return (
      <div className="rounded-lg border border-border/50 bg-card p-3 space-y-2.5 my-2">
        {/* Image grid */}
        <div className={cn('grid gap-2', gridCols)}>
          {images.map((img, i) => (
            <button
              key={i}
              type="button"
              onClick={() => !failedIndexes.has(i) && handlePreview(i)}
              className="relative group overflow-hidden rounded-full border border-border/30 bg-muted/30 p-0 cursor-pointer"
            >
              {failedIndexes.has(i) ? (
                <div className="flex items-center justify-center w-full aspect-square text-muted-foreground text-xs">
                  {t('loadError')}
                </div>
              ) : (
                <>
                  <img
                    src={img.url}
                    alt={`${t('generated')} ${i + 1}`}
                    className="w-full h-auto object-cover transition-transform group-hover:scale-[1.02]"
                    loading="lazy"
                    onError={() => handleImgError(i)}
                  />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
                </>
              )}
            </button>
          ))}
        </div>

        {/* Prompt (collapsible) */}
        {prompt && (
          <button type="button" onClick={() => setPromptExpanded(!promptExpanded)} className="w-full text-left">
            <p className={cn('text-sm text-foreground/80 leading-relaxed', !promptExpanded && 'line-clamp-2')}>
              {prompt}
            </p>
          </button>
        )}

        {/* Reference images */}
        {referenceImageUrls && referenceImageUrls.length > 0 && (
          <div>
            <span className="text-[10px] text-muted-foreground/60 mb-1 block">{t('referenceImages')}</span>
            <div className="flex gap-1.5 flex-wrap">
              {referenceImageUrls.map((refUrl, i) => (
                <div key={i} className="w-12 h-12 rounded border border-border/30 overflow-hidden bg-muted/30">
                  <img src={refUrl} alt={`Reference ${i + 1}`} className="w-full h-full object-cover" loading="lazy" />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Badges + Actions */}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 flex-wrap">
            {model && (
              <Badge variant="secondary" className="text-[10px] gap-1">
                {model}
              </Badge>
            )}
            {size && (
              <Badge variant="outline" className="text-[10px]">
                {size}
              </Badge>
            )}
            {latencyMs != null && (
              <Badge variant="outline" className="text-[10px]">
                {latencyMs < 1000 ? `${latencyMs}ms` : `${(latencyMs / 1000).toFixed(1)}s`}
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => handleDownload(images[0], 0)}
              title={t('download')}
              className="h-7 w-7"
            >
              <DownloadIcon />
            </Button>
            {onEditRequest && images[0] && (
              <Button variant="ghost" size="sm" onClick={() => onEditRequest(images[0].url)} className="h-7 text-xs">
                {t('editThisImage')}
              </Button>
            )}
            {onRegenerate && (
              <Button variant="ghost" size="icon" onClick={onRegenerate} title={t('regenerate')} className="h-7 w-7">
                <RegenerateIcon />
              </Button>
            )}
          </div>
        </div>

        {/* Lightbox */}
        {lightboxIndex !== null && (
          <ImageLightbox
            images={images}
            currentIndex={lightboxIndex}
            onClose={closeLightbox}
            onDownload={handleDownload}
          />
        )}
      </div>
    );
  },
);
ImageResultCard.displayName = 'ImageResultCard';

// -- Lightbox component --

interface ImageLightboxProps {
  images: ImageGenImage[];
  currentIndex: number;
  onClose: () => void;
  onDownload: (img: ImageGenImage, index: number) => void;
}

const ImageLightbox: React.FC<ImageLightboxProps> = memo(({ images, currentIndex, onClose, onDownload }) => {
  const t = useTranslations('imageGen');
  const [index, setIndex] = useState(currentIndex);
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft' && index > 0) setIndex(index - 1);
      if (e.key === 'ArrowRight' && index < images.length - 1) setIndex(index + 1);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [index, images.length, onClose]);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === backdropRef.current) onClose();
    },
    [onClose],
  );

  const img = images[index];
  if (!img) return null;

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
      onClick={handleBackdropClick}
    >
      <div className="relative max-w-[90vw] max-h-[90vh]">
        <img
          src={img.url}
          alt={`${t('generated')} ${index + 1}`}
          className="max-w-full max-h-[85vh] object-contain rounded-lg"
        />

        {/* Controls */}
        <div className="absolute top-2 right-2 flex gap-1">
          <Button
            variant="secondary"
            size="icon"
            onClick={() => onDownload(img, index)}
            className="h-8 w-8 bg-black/50 hover:bg-black/70 text-white"
          >
            <DownloadIcon />
          </Button>
          <Button
            variant="secondary"
            size="icon"
            onClick={onClose}
            className="h-8 w-8 bg-black/50 hover:bg-black/70 text-white"
          >
            <CloseIcon />
          </Button>
        </div>

        {/* Navigation arrows */}
        {images.length > 1 && (
          <>
            {index > 0 && (
              <button
                type="button"
                onClick={() => setIndex(index - 1)}
                className="absolute left-2 top-1/2 -translate-y-1/2 h-10 w-10 rounded-full bg-black/50 hover:bg-black/70 text-white flex items-center justify-center"
              >
                ‹
              </button>
            )}
            {index < images.length - 1 && (
              <button
                type="button"
                onClick={() => setIndex(index + 1)}
                className="absolute right-2 top-1/2 -translate-y-1/2 h-10 w-10 rounded-full bg-black/50 hover:bg-black/70 text-white flex items-center justify-center"
              >
                ›
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
});
ImageLightbox.displayName = 'ImageLightbox';

// -- Inline SVG icons --

const DownloadIcon: React.FC = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

const RegenerateIcon: React.FC = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M21 2v6h-6" />
    <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
    <path d="M3 22v-6h6" />
    <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
  </svg>
);

const CloseIcon: React.FC = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);
