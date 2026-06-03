'use client';

import React, { useState, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Dialog, DialogContent, DialogTitle } from '@/components/primitives/dialog';
import { useTranslations } from 'next-intl';
import { ExternalLink, X, ImageOff } from 'lucide-react';

interface MarkdownImageProps {
  src?: string;
  alt?: string;
}

const MarkdownImage: React.FC<MarkdownImageProps> = ({ src, alt }) => {
  const t = useTranslations('artifacts');
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  const handleLoad = useCallback(() => setLoaded(true), []);
  const handleError = useCallback(() => {
    setLoaded(true);
    setError(true);
  }, []);

  const handleOpenInNewTab = useCallback(() => {
    if (!src) return;
    window.open(src, '_blank', 'noopener,noreferrer');
  }, [src]);

  if (!src) return null;

  if (error) {
    return (
      <div className="inline-flex items-center gap-2 px-4 py-3 rounded-lg bg-muted/50 border border-border/60 text-muted-foreground text-sm my-2">
        <ImageOff size={18} className="flex-shrink-0" />
        <span>{t('imageLoadError')}</span>
      </div>
    );
  }

  return (
    <>
      <span className="block my-3 max-w-xl">
        {!loaded && <span className="block w-full h-48 rounded-lg bg-muted/60 animate-pulse" />}
        <img
          src={src}
          alt={alt || ''}
          loading="lazy"
          onLoad={handleLoad}
          onError={handleError}
          onClick={() => setPreviewOpen(true)}
          className={cn(
            '!m-0 rounded-lg shadow-md border border-border/40 cursor-pointer',
            'transition-opacity duration-300 hover:shadow-lg hover:border-border/60',
            'max-w-full h-auto',
            loaded ? 'opacity-100' : 'opacity-0 h-0 overflow-hidden',
          )}
        />
      </span>

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-[90vw] max-h-[90vh] p-0 gap-0 border-0 bg-transparent shadow-none overflow-hidden [&>button]:hidden">
          <DialogTitle className="sr-only">{alt || 'Image preview'}</DialogTitle>
          <div className="relative flex items-center justify-center">
            <div className="absolute top-3 right-3 z-10 flex gap-2">
              <button
                onClick={handleOpenInNewTab}
                aria-label="Open in new tab"
                className="p-2 rounded-full bg-black/60 text-white hover:bg-black/80 transition-colors backdrop-blur-sm"
              >
                <ExternalLink size={18} />
              </button>
              <button
                onClick={() => setPreviewOpen(false)}
                aria-label="Close preview"
                className="p-2 rounded-full bg-black/60 text-white hover:bg-black/80 transition-colors backdrop-blur-sm"
              >
                <X size={18} />
              </button>
            </div>
            <img src={src} alt={alt || ''} className="max-w-[90vw] max-h-[85vh] object-contain rounded-lg" />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default React.memo(MarkdownImage);
