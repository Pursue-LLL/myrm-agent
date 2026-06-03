'use client';

import React, { useState, useCallback, useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Monitor, X, ZoomIn } from 'lucide-react';
import type { ToolImageOutput } from '@/store/chat/types';

interface ToolImageGalleryProps {
  images: ToolImageOutput[];
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

  useEffect(() => {
    if (lightboxIndex === null) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeLightbox();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [lightboxIndex, closeLightbox]);

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
                src={`data:${img.mimeType};base64,${img.base64}`}
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

      {/* Lightbox overlay */}
      {lightboxIndex !== null && images[lightboxIndex] && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={closeLightbox}
          role="dialog"
          aria-modal="true"
          aria-label="Screenshot preview"
        >
          <button
            type="button"
            onClick={closeLightbox}
            className={cn(
              'absolute top-4 right-4 p-2 rounded-full',
              'bg-white/10 hover:bg-white/20 transition-colors',
              'text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50',
            )}
            aria-label="Close preview"
          >
            <X className="w-5 h-5" />
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`data:${images[lightboxIndex].mimeType};base64,${images[lightboxIndex].base64}`}
            alt={`${images[lightboxIndex].toolName} screenshot full`}
            className="max-w-[95vw] max-h-[85vh] sm:max-w-[90vw] sm:max-h-[90vh] object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
};

export default React.memo(ToolImageGallery);
