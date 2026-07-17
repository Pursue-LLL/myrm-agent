'use client';

/**
 * [INPUT]
 * @aiden0z/pptx-renderer::PptxViewer (POS: PPTX 二进制解析与 HTML/SVG 幻灯片渲染);
 * @/lib/api::getStorageUrl (POS: 存储 URL 构建).
 * [OUTPUT] PptxPreview: 演示文稿高保真预览渲染器。
 * [POS] 通过 pptx-renderer 库将 .pptx 二进制文件解析并渲染为可滚动的幻灯片列表。
 */

import React, { memo, useEffect, useRef, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { getStorageUrl } from '@/lib/api';
import type { PptxViewer } from '@aiden0z/pptx-renderer';

interface PptxPreviewProps {
  previewUrl: string;
}

const PptxPreview: React.FC<PptxPreviewProps> = memo(({ previewUrl }) => {
  const t = useTranslations('artifacts');
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const viewerRef = useRef<PptxViewer | null>(null);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [totalSlides, setTotalSlides] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;

    const load = async () => {
      setLoading(true);
      setError(null);

      try {
        const res = await fetch(getStorageUrl(previewUrl));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const buffer = await res.arrayBuffer();

        if (cancelled) return;

        const { PptxViewer: Viewer, RECOMMENDED_ZIP_LIMITS } = await import('@aiden0z/pptx-renderer');

        container.innerHTML = '';

        const viewer = await Viewer.open(buffer, container, {
          zipLimits: RECOMMENDED_ZIP_LIMITS,
          lazyMedia: true,
          lazySlides: true,
          fitMode: 'contain',
          scrollContainer: container,
          renderMode: 'list',
          listOptions: { windowed: true, showSlideLabels: true },
          onSlideChange: (index: number) => {
            if (!cancelled) setCurrentSlide(index);
          },
        });

        if (cancelled) {
          viewer.destroy();
          return;
        }

        viewerRef.current = viewer;
        setTotalSlides(viewer.slideCount);
        setCurrentSlide(viewer.currentSlideIndex);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
      viewerRef.current?.destroy();
      viewerRef.current = null;
    };
  }, [previewUrl]);

  const handlePrev = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.currentSlideIndex <= 0) return;
    viewer.goToSlide(viewer.currentSlideIndex - 1);
  }, []);

  const handleNext = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.currentSlideIndex >= viewer.slideCount - 1) return;
    viewer.goToSlide(viewer.currentSlideIndex + 1);
  }, []);

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 p-4">
        <p className="text-sm text-destructive">{t('pptxLoadError')}</p>
        <p className="text-xs text-muted-foreground">{error}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-muted/30">
      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
        </div>
      )}

      <div
        ref={containerRef}
        className="flex-1 min-h-0 overflow-auto"
        style={{ display: loading ? 'none' : 'block' }}
      />

      {!loading && totalSlides > 1 && (
        <div className="shrink-0 flex items-center justify-center gap-3 py-2 px-4 border-t border-border bg-background/95 backdrop-blur-sm">
          <button
            onClick={handlePrev}
            disabled={currentSlide === 0}
            className={cn(
              'h-7 px-3 text-xs rounded border border-border transition-colors',
              currentSlide === 0
                ? 'text-muted-foreground/40 cursor-not-allowed'
                : 'text-foreground hover:bg-muted',
            )}
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <span className="text-xs text-muted-foreground tabular-nums">
            {currentSlide + 1} / {totalSlides}
          </span>
          <button
            onClick={handleNext}
            disabled={currentSlide === totalSlides - 1}
            className={cn(
              'h-7 px-3 text-xs rounded border border-border transition-colors',
              currentSlide === totalSlides - 1
                ? 'text-muted-foreground/40 cursor-not-allowed'
                : 'text-foreground hover:bg-muted',
            )}
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
});

PptxPreview.displayName = 'PptxPreview';
export default PptxPreview;
