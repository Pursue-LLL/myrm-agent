'use client';

import React, { useState, useCallback, useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { ChevronLeft, ChevronRight, Download, Monitor, X, ZoomIn } from 'lucide-react';
import type { ToolImageOutput } from '@/store/chat/types';

interface ToolImageGalleryProps {
  images: ToolImageOutput[];
}

const LIGHTBOX_BTN_CLASS = cn(
  'p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors',
  'text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50',
);

function getImageSrc(img: ToolImageOutput): string {
  if (img.url) return img.url;
  return `data:${img.mimeType};base64,${img.base64}`;
}

const ToolImageGallery: React.FC<ToolImageGalleryProps> = ({ images }) => {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const t = useTranslations('chat');

  const openLightbox = useCallback((index: number) => {
    setLightboxIndex(index);
  }, []);

  const closeLightbox = useCallback(() => {
    setLightboxIndex(null);
  }, []);

  const goToPrev = useCallback(() => {
    setLightboxIndex((prev) => (prev !== null && prev > 0 ? prev - 1 : prev));
  }, []);

  const goToNext = useCallback(() => {
    setLightboxIndex((prev) => (prev !== null && prev < images.length - 1 ? prev + 1 : prev));
  }, [images.length]);

  const handleDownload = useCallback(async () => {
    if (lightboxIndex === null) return;
    const img = images[lightboxIndex];
    const ext = img.mimeType.includes('jpeg') || img.mimeType.includes('jpg') ? 'jpg' : 'png';
    const filename = `${img.toolName || 'screenshot'}_${lightboxIndex + 1}.${ext}`;

    const triggerDownload = (href: string) => {
      const a = document.createElement('a');
      a.href = href;
      a.download = filename;
      a.click();
    };

    if (img.url) {
      try {
        const res = await fetch(img.url);
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        triggerDownload(blobUrl);
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
      } catch {
        window.open(img.url, '_blank', 'noopener,noreferrer');
      }
    } else if (img.base64) {
      triggerDownload(`data:${img.mimeType};base64,${img.base64}`);
    }
  }, [lightboxIndex, images]);

  useEffect(() => {
    if (lightboxIndex === null) return;
    document.body.style.overflow = 'hidden';
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeLightbox();
      else if (e.key === 'ArrowLeft') goToPrev();
      else if (e.key === 'ArrowRight') goToNext();
    };
    window.addEventListener('keydown', handler);
    return () => {
      document.body.style.overflow = '';
      window.removeEventListener('keydown', handler);
    };
  }, [lightboxIndex, closeLightbox, goToPrev, goToNext]);

  if (images.length === 0) return null;

  return (
    <>
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Monitor className="w-3.5 h-3.5" />
          <span>{t('toolImage.screenshotLabel')}</span>
        </div>
        <div
          className={cn(
            'grid gap-2',
            images.length === 1 ? 'grid-cols-1 max-w-md' : 'grid-cols-1 sm:grid-cols-2 max-w-2xl',
          )}
        >
          {images.map((img, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => openLightbox(idx)}
              className={cn(
                'group relative overflow-hidden rounded-lg border border-border/60',
                'bg-muted/30 hover:border-primary/40 transition-all duration-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
              )}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={getImageSrc(img)}
                alt={`${img.toolName} screenshot ${idx + 1}`}
                className="w-full h-auto object-contain"
                loading="lazy"
              />
              <div
                className={cn(
                  'absolute inset-0 flex items-center justify-center',
                  'bg-black/0 group-hover:bg-black/20 transition-colors duration-200',
                )}
              >
                <ZoomIn
                  className={cn(
                    'w-6 h-6 text-white drop-shadow-md',
                    'opacity-0 group-hover:opacity-100 transition-opacity duration-200',
                  )}
                />
              </div>
            </button>
          ))}
        </div>
      </div>

      {lightboxIndex !== null && images[lightboxIndex] && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={closeLightbox}
          role="dialog"
          aria-modal="true"
          aria-label="Screenshot preview"
        >
          {/* Top toolbar */}
          <div className="absolute top-4 right-4 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
            <button type="button" onClick={handleDownload} className={LIGHTBOX_BTN_CLASS} aria-label="Download">
              <Download className="w-5 h-5" />
            </button>
            <button type="button" onClick={closeLightbox} className={LIGHTBOX_BTN_CLASS} aria-label="Close preview">
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Left arrow */}
          {images.length > 1 && lightboxIndex > 0 && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                goToPrev();
              }}
              className={cn(LIGHTBOX_BTN_CLASS, 'absolute left-4')}
              aria-label="Previous image"
            >
              <ChevronLeft className="w-6 h-6" />
            </button>
          )}

          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={getImageSrc(images[lightboxIndex])}
            alt={`${images[lightboxIndex].toolName} screenshot full`}
            className="max-w-[95vw] max-h-[85vh] sm:max-w-[90vw] sm:max-h-[90vh] object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />

          {/* Right arrow */}
          {images.length > 1 && lightboxIndex < images.length - 1 && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                goToNext();
              }}
              className={cn(LIGHTBOX_BTN_CLASS, 'absolute right-4')}
              aria-label="Next image"
            >
              <ChevronRight className="w-6 h-6" />
            </button>
          )}

          {/* Counter */}
          {images.length > 1 && (
            <div
              className="absolute bottom-4 text-sm text-white/70 select-none"
              onClick={(e) => e.stopPropagation()}
            >
              {lightboxIndex + 1} / {images.length}
            </div>
          )}
        </div>
      )}
    </>
  );
};

export default React.memo(ToolImageGallery);
