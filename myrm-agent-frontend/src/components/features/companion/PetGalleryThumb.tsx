'use client';

/**
 * PetGalleryThumb — lazy pixel-art thumbnail for Petdex gallery grids.
 *
 * [INPUT]
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind class merge helper)
 *
 * [OUTPUT]
 * - PetGalleryThumb: IntersectionObserver-gated canvas thumbnail
 *
 * [POS]
 * Shared lazy thumbnail renderer for installed and catalog pet tiles.
 */

import { useEffect, useRef, useState } from 'react';

import { cn } from '@/lib/utils/classnameUtils';

const THUMB_SIZE = 64;

export function PetGalleryThumb({ url, alt }: { url: string; alt: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    let cancelled = false;
    let pendingImg: HTMLImageElement | null = null;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || cancelled) {
          return;
        }
        observer.disconnect();

        const img = new Image();
        pendingImg = img;
        img.crossOrigin = 'anonymous';
        img.onload = () => {
          if (cancelled) {
            return;
          }
          const canvas = canvasRef.current;
          if (!canvas) {
            return;
          }
          const ctx = canvas.getContext('2d', { alpha: true });
          if (!ctx) {
            return;
          }
          ctx.imageSmoothingEnabled = false;
          const cellW = Math.min(192, img.naturalWidth);
          const cellH = Math.min(208, img.naturalHeight);
          canvas.width = THUMB_SIZE;
          canvas.height = THUMB_SIZE;
          ctx.drawImage(img, 0, 0, cellW, cellH, 0, 0, THUMB_SIZE, THUMB_SIZE);
          setLoaded(true);
        };
        img.src = url;
      },
      { rootMargin: '200px' },
    );
    observer.observe(container);
    return () => {
      cancelled = true;
      observer.disconnect();
      if (pendingImg) {
        pendingImg.onload = null;
        pendingImg.src = '';
      }
    };
  }, [url]);

  return (
    <div
      ref={containerRef}
      className="flex items-center justify-center"
      style={{ width: THUMB_SIZE, height: THUMB_SIZE }}
    >
      <canvas
        ref={canvasRef}
        className={cn('w-full h-full', !loaded && 'hidden')}
        style={{ imageRendering: 'pixelated' }}
        aria-label={alt}
      />
      {!loaded && <div className="w-full h-full rounded-md bg-muted animate-pulse" />}
    </div>
  );
}
